"""Bidirectional conversion between Anthropic Messages API and OpenAI Chat Completions API.

All functions are pure (no framework dependencies) for easy unit testing.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Request conversion: Anthropic -> OpenAI
# ---------------------------------------------------------------------------

def anthropic_to_openai(
    *,
    model: str,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | None = None,
    **_extra: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert an Anthropic Messages request to OpenAI Chat Completions format.

    Returns (openai_messages, extra_kwargs) where extra_kwargs are additional
    parameters to pass to litellm.acompletion().
    """
    openai_messages: list[dict[str, Any]] = []

    # 1. System prompt
    if system is not None:
        system_text = _extract_system_text(system)
        if system_text:
            openai_messages.append({"role": "system", "content": system_text})

    # 2. Convert messages
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if role == "user":
            openai_messages.extend(_convert_user_message(content))
        elif role == "assistant":
            openai_messages.extend(_convert_assistant_message(content))
        else:
            # Fallback: treat as-is
            openai_messages.append({"role": role, "content": _content_to_string(content)})

    # 3. Ensure first non-system message is user role
    first_non_system = next(
        (m for m in openai_messages if m.get("role") != "system"), None
    )
    if first_non_system is not None and first_non_system.get("role") != "user":
        openai_messages.insert(
            _count_system_messages(openai_messages),
            {"role": "user", "content": "..."},
        )

    # 4. Build extra kwargs
    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if stop_sequences:
        kwargs["stop"] = stop_sequences[0] if len(stop_sequences) == 1 else stop_sequences
    if tools is not None:
        kwargs["tools"] = [_convert_tool(t) for t in tools]
    if tool_choice is not None:
        converted = _convert_tool_choice(tool_choice)
        if converted is not None:
            kwargs["tool_choice"] = converted

    return openai_messages, kwargs


def _extract_system_text(system: str | list[dict[str, Any]]) -> str:
    if isinstance(system, str):
        return system
    parts: list[str] = []
    for block in system:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def _content_to_string(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _convert_user_message(
    content: Any,
) -> list[dict[str, Any]]:
    """Convert an Anthropic user message to one or more OpenAI messages.

    Handles tool_result content blocks by emitting separate tool-role messages.
    """
    if content is None:
        return [{"role": "user", "content": ""}]
    if isinstance(content, str):
        return [{"role": "user", "content": content}]

    if isinstance(content, list):
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
        if not has_tool_result:
            return [{"role": "user", "content": _content_to_string(content)}]

        # Split into text parts and tool_result parts
        messages: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            if block.get("type") == "tool_result":
                # Flush accumulated text first
                if text_parts:
                    messages.append({"role": "user", "content": "\n".join(text_parts)})
                    text_parts = []
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    tool_content = _content_to_string(tool_content)
                messages.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": str(tool_content) if tool_content is not None else "",
                })
            else:
                text_parts.append(_content_to_string([block]))
        if text_parts:
            messages.append({"role": "user", "content": "\n".join(text_parts)})
        return messages

    return [{"role": "user", "content": str(content)}]


def _convert_assistant_message(
    content: Any,
) -> list[dict[str, Any]]:
    """Convert an Anthropic assistant message to OpenAI format.

    Handles tool_use content blocks by emitting tool_calls.
    """
    if content is None:
        return [{"role": "assistant", "content": ""}]
    if isinstance(content, str):
        return [{"role": "assistant", "content": content}]

    if isinstance(content, list):
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
            elif block_type == "tool_use":
                tool_id = block.get("id", f"call_{uuid.uuid4().hex[:24]}")
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                if isinstance(tool_input, dict):
                    arguments = json.dumps(tool_input, ensure_ascii=False)
                else:
                    arguments = str(tool_input)
                tool_calls.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": arguments},
                })
            elif block_type == "thinking":
                pass  # Skip thinking blocks in initial implementation

        msg: dict[str, Any] = {"role": "assistant"}
        msg["content"] = "\n".join(text_parts) if text_parts else None
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if not text_parts and not tool_calls:
            msg["content"] = ""
        return [msg]

    return [{"role": "assistant", "content": str(content)}]


def _convert_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic tool definition to OpenAI function tool format."""
    name = tool.get("name", "")
    description = tool.get("description", "")
    input_schema = tool.get("input_schema", tool.get("parameters", {}))
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def _convert_tool_choice(tool_choice: dict[str, Any]) -> Any:
    """Convert Anthropic tool_choice to OpenAI format."""
    if isinstance(tool_choice, str):
        return tool_choice  # "auto", "none", "required"

    choice_type = tool_choice.get("type", "")
    if choice_type == "auto":
        return "auto"
    if choice_type == "any":
        return "required"
    if choice_type == "none":
        return "none"
    if choice_type == "tool":
        name = tool_choice.get("name", "")
        return {"type": "function", "function": {"name": name}}
    return None


def _count_system_messages(messages: list[dict[str, Any]]) -> int:
    count = 0
    for m in messages:
        if m.get("role") == "system":
            count += 1
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Response conversion: OpenAI -> Anthropic (non-streaming)
# ---------------------------------------------------------------------------

_STOP_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "refusal",
}


def openai_response_to_anthropic(payload: dict[str, Any], model: str) -> dict[str, Any]:
    """Convert an OpenAI Chat Completion response to Anthropic Messages format."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason", "stop")
    usage = payload.get("usage") or {}

    content_blocks: list[dict[str, Any]] = []

    # Text content
    text = message.get("content")
    if text:
        content_blocks.append({"type": "text", "text": text})

    # Tool calls
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function") or {}
            raw_input = fn.get("arguments", "{}")
            try:
                parsed_input = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
            except json.JSONDecodeError:
                parsed_input = raw_input
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "input": parsed_input,
            })

    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    stop_reason = _STOP_REASON_MAP.get(finish_reason, "end_turn")

    return {
        "type": "message",
        "id": msg_id,
        "model": model,
        "role": "assistant",
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# Streaming conversion: OpenAI SSE chunks -> Anthropic SSE events
# ---------------------------------------------------------------------------

class AnthropicStreamState:
    """Mutable state tracker for OpenAI -> Anthropic streaming conversion."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.started = False
        self.content_block_open = False
        self.content_block_index = 0
        self.current_block_type: str | None = None
        self.total_output_tokens = 0

    def _sse_event(self, event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def init_anthropic_stream(state: AnthropicStreamState) -> str:
    """Emit the initial message_start event."""
    state.started = True
    return state._sse_event("message_start", {
        "type": "message_start",
        "message": {
            "type": "message",
            "id": state.msg_id,
            "model": state.model,
            "role": "assistant",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })


def convert_chunk(state: AnthropicStreamState, chunk: dict[str, Any]) -> list[str]:
    """Convert one OpenAI streaming chunk to one or more Anthropic SSE events."""
    events: list[str] = []
    choices = chunk.get("choices") or []
    if not choices:
        return events

    choice = choices[0]
    delta = choice.get("delta") or {}
    finish_reason = choice.get("finish_reason")

    # Strip reasoning_content from delta (same as chat.py)
    delta.pop("reasoning_content", None)
    psf = delta.get("provider_specific_fields")
    if isinstance(psf, dict):
        psf.pop("reasoning_content", None)

    # --- Text content ---
    text_content = delta.get("content")
    if text_content is not None:
        if not state.content_block_open or state.current_block_type != "text":
            # Close previous block if open
            if state.content_block_open:
                events.append(state._sse_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": state.content_block_index,
                }))
                state.content_block_index += 1
            # Open new text block
            events.append(state._sse_event("content_block_start", {
                "type": "content_block_start",
                "index": state.content_block_index,
                "content_block": {"type": "text", "text": ""},
            }))
            state.content_block_open = True
            state.current_block_type = "text"

        events.append(state._sse_event("content_block_delta", {
            "type": "content_block_delta",
            "index": state.content_block_index,
            "delta": {"type": "text_delta", "text": text_content},
        }))
        state.total_output_tokens += 1  # Approximate token counting

    # --- Tool calls ---
    tool_calls = delta.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            # If the tool call has a function name, it's the start of a new tool call
            fn = tc.get("function") or {}
            if fn.get("name"):
                # Close previous block if open
                if state.content_block_open:
                    events.append(state._sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": state.content_block_index,
                    }))
                    state.content_block_index += 1

                events.append(state._sse_event("content_block_start", {
                    "type": "content_block_start",
                    "index": state.content_block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn["name"],
                        "input": {},
                    },
                }))
                state.content_block_open = True
                state.current_block_type = "tool_use"

            # If the tool call has arguments, emit input_json_delta
            arguments = fn.get("arguments")
            if arguments and state.content_block_open and state.current_block_type == "tool_use":
                events.append(state._sse_event("content_block_delta", {
                    "type": "content_block_delta",
                    "index": state.content_block_index,
                    "delta": {"type": "input_json_delta", "partial_json": arguments},
                }))

    # --- Finish ---
    if finish_reason is not None:
        # Close open content block
        if state.content_block_open:
            events.append(state._sse_event("content_block_stop", {
                "type": "content_block_stop",
                "index": state.content_block_index,
            }))
            state.content_block_open = False

        stop_reason = _STOP_REASON_MAP.get(finish_reason, "end_turn")
        events.append(state._sse_event("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": max(state.total_output_tokens, 1)},
        }))
        events.append(state._sse_event("message_stop", {
            "type": "message_stop",
        }))

    return events


# ---------------------------------------------------------------------------
# Error response helpers
# ---------------------------------------------------------------------------

_ERROR_TYPE_MAP: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "api_error",
    503: "overloaded_error",
}


def anthropic_error_response(status_code: int, message: str) -> tuple[dict[str, Any], int]:
    """Build an Anthropic-format error response body and status code."""
    error_type = _ERROR_TYPE_MAP.get(status_code, "api_error")
    return {
        "type": "error",
        "error": {"type": error_type, "message": message},
    }, status_code
