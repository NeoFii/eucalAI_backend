"""OpenAI Responses API protocol adapter."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from app.relay.adapters.responses_convert import (
    ResponsesStreamConverter,
    openai_to_responses_response,
    responses_to_openai_request,
)
from app.relay.upstream import strip_think_tags


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

    def parse_request(
        self, request: Any
    ) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        """Convert Responses request to OpenAI chat format."""
        openai_messages, forward_payload = responses_to_openai_request(request)
        ctx: dict[str, Any] = {}
        return openai_messages, forward_payload, ctx

    def format_error(
        self, status_code: int, message: str, *, error_code: str | None = None
    ) -> JSONResponse:
        """Format error in OpenAI error shape."""
        error_type = {
            401: "invalid_request_error",
            402: "invalid_request_error",
            403: "invalid_request_error",
            429: "rate_limit_error",
        }.get(status_code, "server_error")
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "message": message,
                    "type": error_type,
                    "param": None,
                    "code": error_code,
                }
            },
        )

    def format_non_stream_response(
        self,
        openai_response: dict[str, Any],
        selected_model: str,
        ctx: dict[str, Any],
    ) -> JSONResponse:
        """Convert OpenAI response to Responses API format."""
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
        self, selected_model: str, ctx: dict[str, Any]
    ) -> _ResponsesStreamConverterWrapper:
        """Return Responses stream converter."""
        return _ResponsesStreamConverterWrapper(ResponsesStreamConverter(selected_model))

    def get_timeout(self, is_stream: bool) -> float:
        return 300.0 if is_stream else 45.0
