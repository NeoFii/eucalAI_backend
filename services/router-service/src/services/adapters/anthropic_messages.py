"""Anthropic Messages protocol adapter."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from services.anthropic_convert import (
    AnthropicStreamConverter,
    anthropic_to_openai_request,
    openai_to_anthropic_response,
)


class _AnthropicStreamConverterWrapper:
    """Wraps AnthropicStreamConverter to match the StreamConverter protocol."""

    def __init__(self, inner: AnthropicStreamConverter) -> None:
        self._inner = inner

    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str | None:
        return self._inner.convert_chunk(chunk_dict)

    def get_final_event(self) -> str | None:
        if not self._inner._finished:
            return self._inner._emit_finish("end_turn")
        return None


class AnthropicMessagesAdapter:
    """Adapter for the Anthropic Messages protocol (/v1/anthropic/messages)."""

    @property
    def protocol_name(self) -> str:
        return "messages"

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        openai_messages, forward_payload = anthropic_to_openai_request(request)
        ctx: dict[str, Any] = {"anthropic_request": request}
        return openai_messages, forward_payload, ctx

    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse:
        error_type = {
            429: "rate_limit_error",
            500: "api_error",
            502: "api_error",
            503: "overloaded_error",
        }.get(status_code, "invalid_request_error")
        return JSONResponse(
            status_code=status_code,
            content={"type": "error", "error": {"type": error_type, "message": message}},
        )

    def format_non_stream_response(
        self, openai_response: dict[str, Any], selected_model: str, ctx: dict[str, Any],
    ) -> JSONResponse:
        is_native = ctx.get("is_native_passthrough", False)
        if is_native:
            openai_response["model"] = selected_model
            return JSONResponse(content=openai_response)
        openai_response["model"] = selected_model
        anthropic_response = openai_to_anthropic_response(openai_response, selected_model)
        return JSONResponse(content=anthropic_response)

    def create_stream_converter(
        self, selected_model: str, ctx: dict[str, Any],
    ) -> _AnthropicStreamConverterWrapper | None:
        if ctx.get("is_native_passthrough"):
            return None
        return _AnthropicStreamConverterWrapper(AnthropicStreamConverter(selected_model))

    def get_timeout(self, is_stream: bool) -> float:
        return 45.0
