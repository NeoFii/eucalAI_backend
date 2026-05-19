"""OpenAI Chat Completions protocol adapter."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from api_service.relay.upstream import strip_think_tags


class OpenAIChatAdapter:
    """Adapter for the OpenAI Chat Completions protocol (/v1/chat/completions)."""

    @property
    def protocol_name(self) -> str:
        return "chat"

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        """Extract messages and forward payload from ChatCompletionRequest."""
        messages = list(request.messages or [])
        forward_payload = request.model_dump(
            mode="python",
            exclude={"model", "messages", "stream"},
            exclude_none=True,
        )
        ctx: dict[str, Any] = {"raw_messages": messages}
        return messages, forward_payload, ctx

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
        """Format non-streaming response (OpenAI format is native)."""
        openai_response["model"] = selected_model
        openai_response.pop("provider", None)
        choices = openai_response.get("choices") or []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            choice.pop("provider_specific_fields", None)
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and "<think>" in content:
                    message["content"] = strip_think_tags(content)
                message.pop("reasoning_content", None)
                message.pop("provider_specific_fields", None)
        resp_usage = openai_response.get("usage")
        if isinstance(resp_usage, dict):
            resp_usage.pop("cost_details", None)
            resp_usage.pop("is_byok", None)
        return JSONResponse(content=openai_response)

    def create_stream_converter(
        self, selected_model: str, ctx: dict[str, Any]
    ) -> None:
        """OpenAI native format needs no conversion."""
        return None

    def get_timeout(self, is_stream: bool) -> float:
        return 45.0
