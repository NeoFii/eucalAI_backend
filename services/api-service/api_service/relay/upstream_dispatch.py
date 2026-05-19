"""SDK dispatch: routes upstream calls to the correct SDK backend."""

from __future__ import annotations

from typing import Any

from api_service.core.config import settings
from api_service.relay.backends.anthropic_backend import (
    call_anthropic_from_openai,
    call_anthropic_native,
)
from api_service.relay.backends.openai_backend import call_openai
from api_service.relay.sdk_clients import SdkClientPool


async def dispatch(
    pool: SdkClientPool,
    target_info: dict[str, Any],
    *,
    messages: list[dict[str, Any]],
    forward_payload: dict[str, Any],
    stream: bool,
    timeout: float,
    incoming_protocol: str,
    anthropic_request: Any | None = None,
) -> Any:
    """Route to the correct SDK backend based on provider_slug + incoming_protocol.

    Returns a response object with .model_dump() for non-streaming,
    or an async iterator for streaming.
    """
    provider_slug = target_info.get("provider_slug", "")
    is_anthropic_upstream = provider_slug in settings.ANTHROPIC_NATIVE_SLUGS

    if is_anthropic_upstream:
        if incoming_protocol == "anthropic" and anthropic_request is not None:
            anthropic_params = _build_anthropic_native_params(anthropic_request)
            return await call_anthropic_native(
                pool, target_info, anthropic_params, stream=stream, timeout=timeout,
            )
        return await call_anthropic_from_openai(
            pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
        )

    return await call_openai(
        pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
    )


def _build_anthropic_native_params(request: Any) -> dict[str, Any]:
    """Extract all Anthropic-native fields for direct SDK pass-through."""
    params: dict[str, Any] = {
        "messages": request.messages,
        "max_tokens": request.max_tokens,
    }
    if request.system is not None:
        params["system"] = request.system
    if request.temperature is not None:
        params["temperature"] = request.temperature
    if request.top_p is not None:
        params["top_p"] = request.top_p
    if getattr(request, "top_k", None) is not None:
        params["top_k"] = request.top_k
    if getattr(request, "stop_sequences", None):
        params["stop_sequences"] = request.stop_sequences
    if getattr(request, "tools", None):
        params["tools"] = request.tools
    if getattr(request, "tool_choice", None):
        params["tool_choice"] = request.tool_choice
    if getattr(request, "metadata", None):
        params["metadata"] = request.metadata
    if getattr(request, "thinking", None):
        params["thinking"] = request.thinking
    return params
