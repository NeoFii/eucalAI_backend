"""Streaming generators for relay lifecycle (< 200 lines).

Two paths:
- stream_events: Standard OpenAI-format stream with optional converter
- stream_native_anthropic: Anthropic SDK event pass-through
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.relay.lifecycle.orchestrator import CallLifecycle

logger = logging.getLogger(__name__)


async def stream_events(lifecycle: CallLifecycle, converter: Any) -> AsyncIterator[str]:
    """Standard streaming path — iterates OpenAI SDK chunks."""
    collected_content = ""
    stream_usage: dict = {}
    stream_ok = False
    abort_reason: str | None = None
    t_stream_start = time.monotonic()

    try:
        async for chunk in lifecycle.response:
            chunk_dict = chunk.model_dump(exclude_none=True)
            chunk_dict["model"] = lifecycle.selected_model

            # Extract usage
            chunk_usage = chunk_dict.get("usage")
            if chunk_usage:
                stream_usage = chunk_usage

            # Extract content
            choices = chunk_dict.get("choices") or []
            for c in choices:
                delta = c.get("delta") or {}
                delta.pop("reasoning_content", None)
                delta.pop("provider_specific_fields", None)
                c.pop("provider_specific_fields", None)
                dc = delta.get("content")
                if isinstance(dc, str):
                    collected_content += dc

            # Clean up provider-specific fields
            chunk_dict.pop("provider", None)
            cu = chunk_dict.get("usage")
            if isinstance(cu, dict):
                cu.pop("cost_details", None)
                cu.pop("is_byok", None)

            # Convert and yield
            if converter:
                sse = converter.convert_chunk(chunk_dict)
                if sse:
                    yield sse
            else:
                yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"

        # Final event
        if converter:
            final = converter.get_final_event()
            if final:
                yield final
        else:
            yield "data: [DONE]\n\n"
        stream_ok = True

    except (asyncio.CancelledError, GeneratorExit):
        abort_reason = "client_cancelled"
        raise
    except Exception:
        abort_reason = "stream_error"
    finally:
        from app.relay.lifecycle.finalize import finalize_stream

        await finalize_stream(
            lifecycle, collected_content, stream_usage,
            stream_ok, abort_reason, t_stream_start,
        )


async def stream_native_anthropic(lifecycle: CallLifecycle) -> AsyncIterator[str]:
    """Anthropic native pass-through — preserves original event types."""
    collected_content = ""
    input_tokens = 0
    output_tokens = 0
    stream_ok = False
    abort_reason: str | None = None
    t_stream_start = time.monotonic()

    try:
        async for event in lifecycle.response:
            event_type = event.type
            event_dict = event.model_dump(exclude_none=True)

            if event_type == "message_start":
                msg = event_dict.get("message", {})
                msg["model"] = lifecycle.selected_model
                u = msg.get("usage", {})
                input_tokens = u.get("input_tokens", 0)
            elif event_type == "content_block_delta":
                delta = event_dict.get("delta", {})
                if delta.get("type") == "text_delta":
                    collected_content += delta.get("text", "")
            elif event_type == "message_delta":
                u = event_dict.get("usage", {})
                output_tokens = u.get("output_tokens", output_tokens)

            yield f"event: {event_type}\ndata: {json.dumps(event_dict, ensure_ascii=False)}\n\n"
        stream_ok = True

    except (asyncio.CancelledError, GeneratorExit):
        abort_reason = "client_cancelled"
        raise
    except Exception:
        abort_reason = "stream_error"
    finally:
        stream_usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        } if stream_ok else {}

        from app.relay.lifecycle.finalize import finalize_stream

        await finalize_stream(
            lifecycle, collected_content, stream_usage,
            stream_ok, abort_reason, t_stream_start,
        )
