"""Protocol definitions for multi-protocol adapter pattern."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi.responses import JSONResponse


@runtime_checkable
class StreamConverter(Protocol):
    """Converts OpenAI-format stream chunks to protocol-specific SSE text."""

    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str | None:
        """Convert a single chunk dict to SSE text. Return None to skip."""
        ...

    def get_final_event(self) -> str | None:
        """Return the final SSE event to emit after stream ends, or None."""
        ...


@runtime_checkable
class ProtocolAdapter(Protocol):
    """Adapts protocol-specific request/response formats for the unified call lifecycle."""

    @property
    def protocol_name(self) -> str:
        """Short identifier: 'openai_chat', 'anthropic_messages', 'openai_responses'."""
        ...

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        """Parse protocol-specific request into (openai_messages, forward_payload, context).

        The context dict carries protocol-specific state needed for response formatting
        (e.g., the original Anthropic request for native pass-through detection).
        """
        ...

    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse:
        """Format an error in the protocol-specific envelope."""
        ...

    def format_non_stream_response(
        self, openai_response: dict[str, Any], selected_model: str, ctx: dict[str, Any],
    ) -> JSONResponse:
        """Convert an OpenAI-format response dict to protocol-specific JSON response."""
        ...

    def create_stream_converter(
        self, selected_model: str, ctx: dict[str, Any],
    ) -> StreamConverter | None:
        """Return a stream converter, or None for native OpenAI SSE pass-through."""
        ...

    def get_timeout(self, is_stream: bool) -> float:
        """Return the upstream call timeout in seconds."""
        ...
