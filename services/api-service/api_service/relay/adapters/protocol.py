"""Protocol adapter and stream converter interface definitions.

These are runtime-checkable Protocol classes that define the contract
for protocol-specific adapters (OpenAI Chat, Anthropic Messages, Responses API).
Concrete implementations will be added in Plan 07-02.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from fastapi import Request


@runtime_checkable
class StreamConverter(Protocol):
    """Converts upstream SDK stream chunks to protocol-specific SSE events."""

    def convert_chunk(self, chunk: Any) -> str | None:
        """Convert a single upstream chunk to an SSE data line.

        Returns None if the chunk should be skipped (e.g. empty delta).
        """
        ...

    def get_final_event(self) -> str | None:
        """Return the final SSE event (e.g. [DONE]) or None if not needed."""
        ...


@runtime_checkable
class ProtocolAdapter(Protocol):
    """Adapts incoming requests and outgoing responses for a specific protocol."""

    @property
    def protocol_name(self) -> str:
        """Return the protocol identifier (e.g. 'openai', 'anthropic', 'responses')."""
        ...

    def parse_request(self, body: dict[str, Any]) -> Any:
        """Parse and validate the raw request body into a typed request object."""
        ...

    def format_error(self, status_code: int, message: str, error_type: str = "error") -> dict[str, Any]:
        """Format an error response in the protocol's expected shape."""
        ...

    def format_non_stream_response(self, upstream_response: Any) -> dict[str, Any]:
        """Format a non-streaming upstream response for the client."""
        ...

    def create_stream_converter(self) -> StreamConverter:
        """Create a StreamConverter instance for this protocol."""
        ...

    def get_timeout(self, request: Any) -> float:
        """Return the appropriate timeout for this request."""
        ...
