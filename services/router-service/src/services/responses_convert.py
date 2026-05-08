"""OpenAI Responses API <-> OpenAI Chat Completions format conversion."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from schemas.responses import ResponsesRequest


# ---------------------------------------------------------------------------
# Request conversion: Responses -> Chat Completions
# ---------------------------------------------------------------------------

def _convert_content_parts(content: Any) -> Any:
    """Convert Responses content parts to OpenAI chat format."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content) if content else ""

    oai_parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type", "")
        if ptype in ("input_text", "output_text", "text"):
            oai_parts.append({"type": "text", "text": part.get("text", "")})
        elif ptype == "input_image":
            image_url = part.get("image_url", "")
            if isinstance(image_url, dict):
                image_url = image_url.get("url", "")
            oai_parts.append({"type": "image_url", "image_url": {"url": image_url}})
        elif ptype == "input_file":
            file_info = part.get("file", {})
            if isinstance(file_info, dict) and file_info.get("url"):
                oai_parts.append({"type": "image_url", "image_url": {"url": file_info["url"]}})

    if len(oai_parts) == 1 and oai_parts[0].get("type") == "text":
        return oai_parts[0]["text"]
    return oai_parts if oai_parts else ""


def responses_to_openai_request(
    request: ResponsesRequest,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert a Responses API request to OpenAI chat completions format."""
    openai_messages: list[dict[str, Any]] = []

    # Instructions -> system message
    if request.instructions:
        openai_messages.append({"role": "system", "content": request.instructions})

    # Input conversion
    if isinstance(request.input, str):
        openai_messages.append({"role": "user", "content": request.input})
    elif isinstance(request.input, list):
        pending_tool_calls: list[dict[str, Any]] = []

        for item in request.input:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")
            role = item.get("role", "")

            if item_type == "function_call":
                pending_tool_calls.append({
                    "id": item.get("call_id", ""),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                })

            elif item_type == "function_call_output":
                # Flush pending tool calls as assistant message first
                if pending_tool_calls:
                    openai_messages.append({"role": "assistant", "tool_calls": pending_tool_calls, "content": None})
                    pending_tool_calls = []
                output = item.get("output", "")
                if not isinstance(output, str):
                    output = json.dumps(output, ensure_ascii=False) if output else ""
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": output,
                })

            elif role in ("user", "assistant", "system", "developer"):
                if pending_tool_calls:
                    openai_messages.append({"role": "assistant", "tool_calls": pending_tool_calls, "content": None})
                    pending_tool_calls = []
                actual_role = "system" if role == "developer" else role
                content = _convert_content_parts(item.get("content", ""))
                openai_messages.append({"role": actual_role, "content": content})

        # Flush remaining tool calls
        if pending_tool_calls:
            openai_messages.append({"role": "assistant", "tool_calls": pending_tool_calls, "content": None})

    # Build forward payload
    forward_payload: dict[str, Any] = {}
    if request.max_output_tokens is not None:
        forward_payload["max_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        forward_payload["temperature"] = request.temperature
    if request.top_p is not None:
        forward_payload["top_p"] = request.top_p
    if request.tools:
        forward_payload["tools"] = request.tools
    if request.tool_choice is not None:
        forward_payload["tool_choice"] = request.tool_choice
    if request.parallel_tool_calls is not None:
        forward_payload["parallel_tool_calls"] = request.parallel_tool_calls

    return openai_messages, forward_payload


# ---------------------------------------------------------------------------
# Response conversion: Chat Completions -> Responses (non-streaming)
# ---------------------------------------------------------------------------

def openai_to_responses_response(
    openai_resp: dict[str, Any],
    selected_model: str,
) -> dict[str, Any]:
    """Convert an OpenAI chat completion response to Responses API format."""
    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
    msg_id = f"msg_{uuid.uuid4().hex[:20]}"
    created_at = openai_resp.get("created", int(time.time()))

    choices = openai_resp.get("choices") or []
    output: list[dict[str, Any]] = []

    if choices:
        choice = choices[0]
        message = choice.get("message", {})
        text_content = message.get("content", "")
        tool_calls = message.get("tool_calls")

        # Text output
        if text_content:
            output.append({
                "type": "message",
                "id": msg_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text_content, "annotations": []}],
            })

        # Tool call outputs
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                output.append({
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:20]}",
                    "call_id": tc.get("id", f"call_{uuid.uuid4().hex[:20]}"),
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", "{}"),
                    "status": "completed",
                })

    if not output:
        output.append({
            "type": "message",
            "id": msg_id,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "", "annotations": []}],
        })

    usage = openai_resp.get("usage", {})
    responses_usage = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return {
        "id": resp_id,
        "object": "response",
        "created_at": created_at,
        "status": "completed",
        "model": selected_model,
        "output": output,
        "parallel_tool_calls": True,
        "temperature": 1.0,
        "top_p": 1.0,
        "usage": responses_usage,
    }


# ---------------------------------------------------------------------------
# Streaming conversion: Chat Completions SSE -> Responses SSE
# ---------------------------------------------------------------------------

def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ResponsesStreamConverter:
    """Converts OpenAI streaming chunks into Responses API SSE events."""

    def __init__(self, selected_model: str):
        self._model = selected_model
        self._resp_id = f"resp_{uuid.uuid4().hex[:24]}"
        self._msg_id = f"msg_{uuid.uuid4().hex[:20]}"
        self._created_at = int(time.time())
        self._started = False
        self._text_started = False
        self._text_content = ""
        self._tool_calls: dict[int, dict[str, Any]] = {}
        self._tool_started: set[int] = set()
        self._finished = False
        self._usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def _emit_created(self) -> str:
        self._started = True
        resp_obj = {
            "id": self._resp_id,
            "object": "response",
            "created_at": self._created_at,
            "status": "in_progress",
            "model": self._model,
            "output": [],
            "usage": None,
        }
        return _sse_event("response.created", {"type": "response.created", "response": resp_obj})

    def _emit_output_item_added_message(self) -> str:
        self._text_started = True
        item = {
            "type": "message",
            "id": self._msg_id,
            "status": "in_progress",
            "role": "assistant",
            "content": [],
        }
        events = _sse_event("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": item,
        })
        events += _sse_event("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": self._msg_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        })
        return events

    def _emit_text_delta(self, text: str) -> str:
        self._text_content += text
        return _sse_event("response.output_text.delta", {
            "type": "response.output_text.delta",
            "item_id": self._msg_id,
            "output_index": 0,
            "content_index": 0,
            "delta": text,
        })

    def _emit_text_done(self) -> str:
        events = _sse_event("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": self._msg_id,
            "output_index": 0,
            "content_index": 0,
            "text": self._text_content,
        })
        events += _sse_event("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": self._msg_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": self._text_content, "annotations": []},
        })
        events += _sse_event("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": self._msg_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": self._text_content, "annotations": []}],
            },
        })
        return events

    def _emit_tool_added(self, tc_index: int, call_id: str, name: str) -> str:
        self._tool_started.add(tc_index)
        output_index = (1 if self._text_started else 0) + tc_index
        fc_id = f"fc_{uuid.uuid4().hex[:20]}"
        self._tool_calls[tc_index] = {"id": fc_id, "call_id": call_id, "name": name, "arguments": "", "output_index": output_index}
        item = {
            "type": "function_call",
            "id": fc_id,
            "call_id": call_id,
            "name": name,
            "arguments": "",
            "status": "in_progress",
        }
        return _sse_event("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": item,
        })

    def _emit_tool_args_delta(self, tc_index: int, delta: str) -> str:
        tc = self._tool_calls.get(tc_index, {})
        tc["arguments"] = tc.get("arguments", "") + delta
        return _sse_event("response.function_call_arguments.delta", {
            "type": "response.function_call_arguments.delta",
            "item_id": tc.get("id", ""),
            "output_index": tc.get("output_index", 0),
            "delta": delta,
        })

    def _emit_tool_done(self, tc_index: int) -> str:
        tc = self._tool_calls.get(tc_index, {})
        output_index = tc.get("output_index", 0)
        events = _sse_event("response.function_call_arguments.done", {
            "type": "response.function_call_arguments.done",
            "item_id": tc.get("id", ""),
            "output_index": output_index,
            "arguments": tc.get("arguments", ""),
        })
        events += _sse_event("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {
                "type": "function_call",
                "id": tc.get("id", ""),
                "call_id": tc.get("call_id", ""),
                "name": tc.get("name", ""),
                "arguments": tc.get("arguments", ""),
                "status": "completed",
            },
        })
        return events

    def _emit_completed(self) -> str:
        self._finished = True
        output: list[dict[str, Any]] = []
        if self._text_started:
            output.append({
                "type": "message",
                "id": self._msg_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": self._text_content, "annotations": []}],
            })
        for tc in self._tool_calls.values():
            output.append({
                "type": "function_call",
                "id": tc.get("id", ""),
                "call_id": tc.get("call_id", ""),
                "name": tc.get("name", ""),
                "arguments": tc.get("arguments", ""),
                "status": "completed",
            })

        resp_obj = {
            "id": self._resp_id,
            "object": "response",
            "created_at": self._created_at,
            "status": "completed",
            "model": self._model,
            "output": output,
            "usage": self._usage,
        }
        return _sse_event("response.completed", {"type": "response.completed", "response": resp_obj})

    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str:
        """Convert a single OpenAI streaming chunk to Responses SSE events."""
        if self._finished:
            return ""

        events = ""

        # Capture usage
        chunk_usage = chunk_dict.get("usage")
        if chunk_usage:
            self._usage = {
                "input_tokens": chunk_usage.get("prompt_tokens", 0),
                "output_tokens": chunk_usage.get("completion_tokens", 0),
                "total_tokens": chunk_usage.get("total_tokens", 0),
            }

        # Emit created on first chunk
        if not self._started:
            events += self._emit_created()

        choices = chunk_dict.get("choices") or []
        if not choices:
            if chunk_usage and self._started and not self._finished:
                if self._text_started:
                    events += self._emit_text_done()
                for idx in self._tool_started:
                    events += self._emit_tool_done(idx)
                events += self._emit_completed()
            return events

        choice = choices[0]
        delta = choice.get("delta") or {}
        finish_reason = choice.get("finish_reason")

        # Text content
        text = delta.get("content")
        if text:
            if not self._text_started:
                events += self._emit_output_item_added_message()
            events += self._emit_text_delta(text)

        # Tool calls
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                tc_index = tc.get("index", 0)
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                tc_name = func.get("name", "")
                tc_args = func.get("arguments", "")

                if tc_index not in self._tool_started:
                    if not tc_id:
                        tc_id = f"call_{uuid.uuid4().hex[:20]}"
                    events += self._emit_tool_added(tc_index, tc_id, tc_name)

                if tc_args:
                    events += self._emit_tool_args_delta(tc_index, tc_args)

        # Finish
        if finish_reason:
            if self._text_started:
                events += self._emit_text_done()
            for idx in sorted(self._tool_started):
                events += self._emit_tool_done(idx)
            events += self._emit_completed()

        return events
