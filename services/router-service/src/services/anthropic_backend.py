"""Anthropic SDK backend: direct calls to Anthropic-native upstreams."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from services.sdk_clients import SdkClientPool


# ---------------------------------------------------------------------------
# Response wrappers (match litellm interface: .model_dump())
# ---------------------------------------------------------------------------

@dataclass
class AnthropicAsOpenAIResponse:
    """Anthropic response normalized to OpenAI chat completion dict shape."""

    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


@dataclass
class AnthropicAsOpenAIStreamChunk:
    """Single streaming chunk normalized to OpenAI shape."""

    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


@dataclass
class AnthropicNativeResponse:
    """Raw Anthropic response for pass-through path."""

    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


# ---------------------------------------------------------------------------
# Stop reason mapping
# ---------------------------------------------------------------------------

_ANTHROPIC_TO_OPENAI_STOP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


# ---------------------------------------------------------------------------
# Native pass-through call (Anthropic in → Anthropic upstream)
# ---------------------------------------------------------------------------

async def call_anthropic_native(
    pool: SdkClientPool,
    target_info: dict[str, Any],
    anthropic_params: dict[str, Any],
    *,
    stream: bool,
    timeout: float = 45.0,
) -> AnthropicNativeResponse | AsyncIterator[Any]:
    """Call Anthropic upstream with native params (pass-through, no conversion).

    Returns AnthropicNativeResponse for non-streaming, or the SDK async stream.
    """
    client: AsyncAnthropic = pool.get_anthropic(
        target_info["api_base"], target_info["api_key"]
    )

    kwargs: dict[str, Any] = {
        "model": target_info["upstream_model"],
        "stream": stream,
        "timeout": timeout,
        **anthropic_params,
    }

    if stream:
        raw_stream = await client.messages.create(**kwargs)
        return raw_stream
    response = await client.messages.create(**kwargs)
    return AnthropicNativeResponse(_data=response.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Cross-protocol call (OpenAI in → Anthropic upstream, response normalized)
# ---------------------------------------------------------------------------

async def call_anthropic_from_openai(
    pool: SdkClientPool,
    target_info: dict[str, Any],
    messages: list[dict[str, Any]],
    forward_payload: dict[str, Any],
    *,
    stream: bool,
    timeout: float = 45.0,
) -> AnthropicAsOpenAIResponse | AsyncIterator[AnthropicAsOpenAIStreamChunk]:
    """Call Anthropic upstream, converting OpenAI params and normalizing response."""
    client: AsyncAnthropic = pool.get_anthropic(
        target_info["api_base"], target_info["api_key"]
    )

    anthropic_params = _openai_to_anthropic_params(messages, forward_payload)
    kwargs: dict[str, Any] = {
        "model": target_info["upstream_model"],
        "stream": stream,
        "timeout": timeout,
        **anthropic_params,
    }

    if stream:
        raw_stream = await client.messages.create(**kwargs)
        return _normalize_stream(raw_stream)

    response = await client.messages.create(**kwargs)
    resp_dict = response.model_dump(exclude_none=True)
    return AnthropicAsOpenAIResponse(_data=_anthropic_resp_to_openai(resp_dict))


# ---------------------------------------------------------------------------
# OpenAI params → Anthropic params conversion
# ---------------------------------------------------------------------------

def _openai_to_anthropic_params(
    messages: list[dict[str, Any]],
    forward_payload: dict[str, Any],
) -> dict[str, Any]:
    """Convert OpenAI chat messages + payload to Anthropic messages.create() params."""
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        system_parts.append(part.get("text", ""))
            continue

        if role == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }],
            })
            continue

        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        blocks.append({"type": "text", "text": part.get("text", "")})
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    try:
                        input_data = json.loads(func.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        input_data = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                        "name": func.get("name", ""),
                        "input": input_data,
                    })
            anthropic_messages.append({"role": "assistant", "content": blocks or ""})
            continue

        # user message
        if isinstance(content, str):
            anthropic_messages.append({"role": "user", "content": content})
        elif isinstance(content, list):
            blocks = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    blocks.append({"type": "text", "text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    if url.startswith("data:"):
                        media_type, _, b64 = url.partition(";base64,")
                        media_type = media_type.replace("data:", "")
                        blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64},
                        })
                    else:
                        blocks.append({
                            "type": "image",
                            "source": {"type": "url", "url": url},
                        })
            anthropic_messages.append({"role": "user", "content": blocks})
        else:
            anthropic_messages.append({"role": "user", "content": str(content)})

    params: dict[str, Any] = {
        "messages": anthropic_messages,
        "max_tokens": forward_payload.get("max_tokens", 4096),
    }

    if system_parts:
        params["system"] = "\n".join(system_parts)
    if forward_payload.get("temperature") is not None:
        params["temperature"] = forward_payload["temperature"]
    if forward_payload.get("top_p") is not None:
        params["top_p"] = forward_payload["top_p"]
    if forward_payload.get("stop"):
        params["stop_sequences"] = forward_payload["stop"]

    oai_tools = forward_payload.get("tools")
    if oai_tools:
        anthropic_tools = []
        for tool in oai_tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        params["tools"] = anthropic_tools

    tc = forward_payload.get("tool_choice")
    if tc == "auto":
        params["tool_choice"] = {"type": "auto"}
    elif tc == "required":
        params["tool_choice"] = {"type": "any"}
    elif isinstance(tc, dict) and tc.get("type") == "function":
        params["tool_choice"] = {
            "type": "tool",
            "name": tc.get("function", {}).get("name", ""),
        }

    return params


# ---------------------------------------------------------------------------
# Anthropic response → OpenAI response normalization
# ---------------------------------------------------------------------------

def _anthropic_resp_to_openai(resp: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic Messages response dict to OpenAI chat completion dict."""
    content_blocks = resp.get("content", [])
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in content_blocks:
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "thinking":
            thinking_text = block.get("thinking", "")
            if thinking_text:
                text_parts.insert(0, f"<think>{thinking_text}</think>")
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                },
            })

    message: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts) or None}
    if tool_calls:
        message["tool_calls"] = tool_calls

    stop_reason = resp.get("stop_reason", "end_turn")
    finish_reason = _ANTHROPIC_TO_OPENAI_STOP.get(stop_reason, "stop")

    usage = resp.get("usage", {})
    openai_usage: dict[str, Any] = {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }
    cache_read = usage.get("cache_read_input_tokens", 0)
    if cache_read:
        openai_usage["cached_tokens"] = cache_read

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "model": resp.get("model", ""),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": openai_usage,
    }


# ---------------------------------------------------------------------------
# Streaming normalization (Anthropic events → OpenAI chunks)
# ---------------------------------------------------------------------------

async def _normalize_stream(
    raw_stream: Any,
) -> AsyncIterator[AnthropicAsOpenAIStreamChunk]:
    """Convert Anthropic streaming events to OpenAI-shaped chunk dicts."""
    input_tokens = 0
    output_tokens = 0

    async for event in raw_stream:
        event_type = event.type

        if event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg:
                usage = getattr(msg, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "input_tokens", 0)
            continue

        if event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is None:
                continue
            delta_type = getattr(delta, "type", "")
            if delta_type == "text_delta":
                text = getattr(delta, "text", "")
                yield AnthropicAsOpenAIStreamChunk(_data={
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                })
            elif delta_type == "thinking_delta":
                thinking = getattr(delta, "thinking", "")
                yield AnthropicAsOpenAIStreamChunk(_data={
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"<think>{thinking}"},
                        "finish_reason": None,
                    }],
                })
            elif delta_type == "input_json_delta":
                partial = getattr(delta, "partial_json", "")
                index = getattr(event, "index", 0)
                yield AnthropicAsOpenAIStreamChunk(_data={
                    "choices": [{
                        "index": 0,
                        "delta": {"tool_calls": [{"index": index, "function": {"arguments": partial}}]},
                        "finish_reason": None,
                    }],
                })

        elif event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block and getattr(block, "type", "") == "tool_use":
                index = getattr(event, "index", 0)
                yield AnthropicAsOpenAIStreamChunk(_data={
                    "choices": [{
                        "index": 0,
                        "delta": {"tool_calls": [{
                            "index": index,
                            "id": getattr(block, "id", ""),
                            "type": "function",
                            "function": {"name": getattr(block, "name", ""), "arguments": ""},
                        }]},
                        "finish_reason": None,
                    }],
                })

        elif event_type == "message_delta":
            delta = getattr(event, "delta", None)
            stop_reason = getattr(delta, "stop_reason", "end_turn") if delta else "end_turn"
            finish_reason = _ANTHROPIC_TO_OPENAI_STOP.get(stop_reason, "stop")
            usage_obj = getattr(event, "usage", None)
            if usage_obj:
                output_tokens = getattr(usage_obj, "output_tokens", 0)
            yield AnthropicAsOpenAIStreamChunk(_data={
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            })
