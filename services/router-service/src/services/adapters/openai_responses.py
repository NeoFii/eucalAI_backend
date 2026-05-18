"""OpenAI Responses API protocol adapter."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from services.responses_convert import (
    ResponsesStreamConverter,
    openai_to_responses_response,
    responses_to_openai_request,
)
from services.upstream import strip_think_tags


class _ResponsesStreamConverterWrapper:
    """Wraps ResponsesStreamConverter to match the StreamConverter protocol."""

    def __init__(self, inner: ResponsesStreamConverter) -> None:
        self._inner = inner

    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str | None:
        return self._inner.convert_chunk(chunk_dict)

    def get_final_event(self) -> str | None:
        if not self._inner._finished:
            if self._inner._pending_finish:
                return self._inner._emit_completed()
            else:
                parts = ""
                if self._inner._text_started:
                    parts += self._inner._emit_text_done()
                parts += self._inner._emit_completed()
                return parts
        return None


class OpenAIResponsesAdapter:
    """Adapter for the OpenAI Responses protocol (/v1/responses)."""

    @property
    def protocol_name(self) -> str:
        return "responses"

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        openai_messages, forward_payload = responses_to_openai_request(request)
        ctx: dict[str, Any] = {}
        return openai_messages, forward_payload, ctx

    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse:
        error_type = {
            401: "invalid_request_error",
            402: "invalid_request_error",
            403: "invalid_request_error",
            429: "rate_limit_error",
        }.get(status_code, "server_error")
        return JSONResponse(
            status_code=status_code,
            content={"error": {"message": message, "type": error_type, "param": None, "code": error_code}},
        )

    def format_non_stream_response(
        self, openai_response: dict[str, Any], selected_model: str, ctx: dict[str, Any],
    ) -> JSONResponse:
        openai_response["model"] = selected_model
        choices = openai_response.get("choices") or []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and "<think>" in content:
                    message["content"] = strip_think_tags(content)
        responses_response = openai_to_responses_response(openai_response, selected_model)
        return JSONResponse(content=responses_response)

    def create_stream_converter(
        self, selected_model: str, ctx: dict[str, Any],
    ) -> _ResponsesStreamConverterWrapper:
        return _ResponsesStreamConverterWrapper(ResponsesStreamConverter(selected_model))

    def get_timeout(self, is_stream: bool) -> float:
        return 300.0 if is_stream else 45.0

    def format_error_stream(self, selected_model: str) -> Any:
        """Return an async generator that emits a minimal error-stream for upstream failures."""
        converter = ResponsesStreamConverter(selected_model)

        async def _error_stream():
            yield converter._emit_created()
            yield converter._emit_completed()

        return _error_stream()
