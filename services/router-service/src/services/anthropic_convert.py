"""Anthropic <-> OpenAI format conversion utilities."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, AsyncGenerator

from schemas.anthropic import AnthropicMessagesRequest

_THINK_TAG_RE = re.compile(r"<think>([\s\S]*?)</think>\s*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Stop reason mapping
# ---------------------------------------------------------------------------

_OPENAI_TO_ANTHROPIC_STOP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "max_tokens": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "end_turn",
}

_ANTHROPIC_TO_OPENAI_STOP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


# ---------------------------------------------------------------------------
# Request conversion: Anthropic -> OpenAI
# ---------------------------------------------------------------------------

def anthropic_to_openai_request(
    request: AnthropicMessagesRequest,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert an Anthropic Messages request to OpenAI chat format.

    Returns (openai_messages, forward_payload).
    """
    openai_messages: list[dict[str, Any]] = []

    # System message
    if request.system:
        if isinstance(request.system, str):
            openai_messages.append({"role": "system", "content": request.system})
        elif isinstance(request.system, list):
            text_parts = []
            for block in request.system:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            if text_parts:
                openai_messages.append({"role": "system", "content": "\n".join(text_parts)})

    # Convert messages
    for msg in request.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            openai_messages.append({"role": role, "content": str(content)})
            continue

        oai_content: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")

            if block_type == "text":
                oai_content.append({"type": "text", "text": block.get("text", "")})

            elif block_type == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    data_url = f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                    oai_content.append({"type": "image_url", "image_url": {"url": data_url}})
                elif source.get("type") == "url":
                    oai_content.append({"type": "image_url", "image_url": {"url": source.get("url", "")}})

            elif block_type == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })

            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    parts = []
                    for sub in tool_content:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            parts.append(sub.get("text", ""))
                    tool_content = "\n".join(parts)
                elif not isinstance(tool_content, str):
                    tool_content = str(tool_content) if tool_content else ""
                if block.get("is_error"):
                    tool_content = f"[TOOL_ERROR] {tool_content}"
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": tool_content,
                })

        if role == "assistant" and tool_calls:
            assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            if oai_content:
                if len(oai_content) == 1 and oai_content[0].get("type") == "text":
                    assistant_msg["content"] = oai_content[0]["text"]
                else:
                    assistant_msg["content"] = oai_content
            openai_messages.append(assistant_msg)
        elif oai_content:
            if len(oai_content) == 1 and oai_content[0].get("type") == "text":
                openai_messages.append({"role": role, "content": oai_content[0]["text"]})
            else:
                openai_messages.append({"role": role, "content": oai_content})

        for tr in tool_results:
            openai_messages.append(tr)

    # Build forward payload
    forward_payload: dict[str, Any] = {"max_tokens": request.max_tokens}

    if request.temperature is not None:
        forward_payload["temperature"] = request.temperature
    if request.top_p is not None:
        forward_payload["top_p"] = request.top_p
    if request.top_k is not None:
        forward_payload["top_k"] = request.top_k
    if request.stop_sequences:
        forward_payload["stop"] = request.stop_sequences
    if request.metadata and request.metadata.get("user_id"):
        forward_payload["user"] = request.metadata["user_id"]

    # Tools conversion
    if request.tools:
        oai_tools = []
        for tool in request.tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        forward_payload["tools"] = oai_tools

    # Tool choice mapping
    if request.tool_choice:
        tc_type = request.tool_choice.get("type", "auto")
        if tc_type == "auto":
            forward_payload["tool_choice"] = "auto"
        elif tc_type == "any":
            forward_payload["tool_choice"] = "required"
        elif tc_type == "tool":
            forward_payload["tool_choice"] = {
                "type": "function",
                "function": {"name": request.tool_choice.get("name", "")},
            }

    # Extended thinking
    if request.thinking:
        forward_payload["thinking"] = request.thinking

    return openai_messages, forward_payload


# ---------------------------------------------------------------------------
# Response conversion: OpenAI -> Anthropic (non-streaming)
# ---------------------------------------------------------------------------

def openai_to_anthropic_response(
    openai_resp: dict[str, Any],
    selected_model: str,
) -> dict[str, Any]:
    """Convert an OpenAI chat completion response to Anthropic Messages format."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    choices = openai_resp.get("choices") or []
    content_blocks: list[dict[str, Any]] = []
    stop_reason = "end_turn"

    if choices:
        choice = choices[0]
        finish_reason = choice.get("finish_reason", "stop")
        stop_reason = _OPENAI_TO_ANTHROPIC_STOP.get(finish_reason, "end_turn")
        message = choice.get("message", {})

        text_content = message.get("content")
        if text_content:
            think_match = _THINK_TAG_RE.search(text_content)
            if think_match:
                thinking_text = think_match.group(1).strip()
                if thinking_text:
                    content_blocks.append({"type": "thinking", "thinking": thinking_text})
                clean_text = _THINK_TAG_RE.sub("", text_content).strip()
                if clean_text:
                    content_blocks.append({"type": "text", "text": clean_text})
            else:
                content_blocks.append({"type": "text", "text": text_content})

        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                try:
                    input_data = json.loads(func.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    input_data = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                    "name": func.get("name", ""),
                    "input": input_data,
                })

    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    usage = openai_resp.get("usage", {})
    anthropic_usage = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": selected_model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": anthropic_usage,
    }


# ---------------------------------------------------------------------------
# Streaming conversion: OpenAI SSE -> Anthropic SSE
# ---------------------------------------------------------------------------

def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class AnthropicStreamConverter:
    """Converts OpenAI streaming chunks into Anthropic SSE events."""

    def __init__(self, selected_model: str):
        self._model = selected_model
        self._msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        self._content_index = 0
        self._block_open = False
        self._block_type: str | None = None
        self._tool_index_map: dict[int, int] = {}
        self._started = False
        self._finished = False
        self._usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        self._think_state: str = "idle"  # idle | buffering | thinking | done
        self._think_buffer: str = ""

    def _emit_message_start(self, usage_hint: dict | None = None) -> str:
        self._started = True
        input_tokens = 0
        if usage_hint:
            input_tokens = usage_hint.get("prompt_tokens", 0)
            self._usage["input_tokens"] = input_tokens
        return _sse_event("message_start", {
            "type": "message_start",
            "message": {
                "id": self._msg_id,
                "type": "message",
                "role": "assistant",
                "model": self._model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        }) + _sse_event("ping", {"type": "ping"})

    def _emit_block_start_text(self) -> str:
        event = _sse_event("content_block_start", {
            "type": "content_block_start",
            "index": self._content_index,
            "content_block": {"type": "text", "text": ""},
        })
        self._block_open = True
        self._block_type = "text"
        return event

    def _emit_block_start_thinking(self) -> str:
        event = _sse_event("content_block_start", {
            "type": "content_block_start",
            "index": self._content_index,
            "content_block": {"type": "thinking", "thinking": ""},
        })
        self._block_open = True
        self._block_type = "thinking"
        return event

    def _emit_thinking_delta(self, text: str) -> str:
        return _sse_event("content_block_delta", {
            "type": "content_block_delta",
            "index": self._content_index,
            "delta": {"type": "thinking_delta", "thinking": text},
        })

    def _emit_block_start_tool(self, tool_id: str, name: str) -> str:
        event = _sse_event("content_block_start", {
            "type": "content_block_start",
            "index": self._content_index,
            "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}},
        })
        self._block_open = True
        self._block_type = "tool_use"
        return event

    def _emit_block_stop(self) -> str:
        event = _sse_event("content_block_stop", {
            "type": "content_block_stop",
            "index": self._content_index,
        })
        self._block_open = False
        self._block_type = None
        self._content_index += 1
        return event

    def _emit_text_delta(self, text: str) -> str:
        return _sse_event("content_block_delta", {
            "type": "content_block_delta",
            "index": self._content_index,
            "delta": {"type": "text_delta", "text": text},
        })

    def _emit_tool_json_delta(self, index: int, partial: str) -> str:
        block_idx = self._tool_index_map.get(index, self._content_index)
        return _sse_event("content_block_delta", {
            "type": "content_block_delta",
            "index": block_idx,
            "delta": {"type": "input_json_delta", "partial_json": partial},
        })

    def _emit_finish(self, stop_reason: str) -> str:
        events = ""
        events += self.flush_think_buffer()
        if self._block_open:
            events += self._emit_block_stop()
        events += _sse_event("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": self._usage.get("output_tokens", 0)},
        })
        events += _sse_event("message_stop", {"type": "message_stop"})
        self._finished = True
        return events

    def _process_text(self, text: str) -> str:
        """Route text through think-tag state machine."""
        events = ""
        remaining = text

        while remaining:
            if self._think_state == "idle":
                # Check if text starts with or contains <think>
                self._think_buffer += remaining
                remaining = ""
                if "<think>" in self._think_buffer:
                    before, _, after = self._think_buffer.partition("<think>")
                    if before.strip():
                        events += self._emit_plain_text(before)
                    self._think_state = "thinking"
                    events += self._start_thinking_block()
                    self._think_buffer = ""
                    remaining = after
                elif len(self._think_buffer) >= 7:
                    # Can't be a partial <think> tag, flush safe portion
                    safe = self._think_buffer[:-6]
                    self._think_buffer = self._think_buffer[-6:]
                    if safe:
                        events += self._emit_plain_text(safe)
                # else: keep buffering (could be partial "<thi...")

            elif self._think_state == "thinking":
                if "</think>" in remaining:
                    before, _, after = remaining.partition("</think>")
                    if before:
                        events += self._emit_thinking_delta(before)
                    events += self._emit_block_stop()
                    self._think_state = "done"
                    remaining = after
                else:
                    events += self._emit_thinking_delta(remaining)
                    remaining = ""

            elif self._think_state == "done":
                # After thinking, all remaining text is normal content
                events += self._emit_plain_text(remaining)
                remaining = ""

        return events

    def _start_thinking_block(self) -> str:
        if self._block_open:
            return self._emit_block_stop() + self._emit_block_start_thinking()
        return self._emit_block_start_thinking()

    def _emit_plain_text(self, text: str) -> str:
        events = ""
        if not self._block_open or self._block_type != "text":
            if self._block_open:
                events += self._emit_block_stop()
            events += self._emit_block_start_text()
        events += self._emit_text_delta(text)
        return events

    def flush_think_buffer(self) -> str:
        """Flush any remaining buffered text (call at stream end)."""
        if self._think_buffer and self._think_state == "idle":
            events = self._emit_plain_text(self._think_buffer)
            self._think_buffer = ""
            return events
        return ""

    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str:
        """Convert a single OpenAI streaming chunk to Anthropic SSE event string(s)."""
        if self._finished:
            return ""

        events = ""

        # Capture usage from usage-only chunks
        chunk_usage = chunk_dict.get("usage")
        if chunk_usage:
            self._usage["input_tokens"] = chunk_usage.get("prompt_tokens", 0)
            self._usage["output_tokens"] = chunk_usage.get("completion_tokens", 0)

        # Emit message_start on first chunk
        if not self._started:
            events += self._emit_message_start(chunk_usage)

        choices = chunk_dict.get("choices") or []
        if not choices:
            # Usage-only final chunk (no choices) — emit finish
            if chunk_usage and self._started and not self._finished:
                stop_reason = "end_turn"
                events += self._emit_finish(stop_reason)
            return events

        choice = choices[0]
        delta = choice.get("delta") or {}
        finish_reason = choice.get("finish_reason")

        # Text content
        text = delta.get("content")
        if text:
            events += self._process_text(text)

        # Tool calls
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                tc_index = tc.get("index", 0)
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                tc_name = func.get("name", "")
                tc_args = func.get("arguments", "")

                if tc_index not in self._tool_index_map:
                    # New tool call — close previous block, start new one
                    if self._block_open:
                        events += self._emit_block_stop()
                    if not tc_id:
                        tc_id = f"toolu_{uuid.uuid4().hex[:24]}"
                    events += self._emit_block_start_tool(tc_id, tc_name)
                    self._tool_index_map[tc_index] = self._content_index

                if tc_args:
                    events += self._emit_tool_json_delta(tc_index, tc_args)

        # Finish
        if finish_reason:
            stop_reason = _OPENAI_TO_ANTHROPIC_STOP.get(finish_reason, "end_turn")
            events += self._emit_finish(stop_reason)

        return events
