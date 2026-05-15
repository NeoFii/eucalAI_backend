"""SDK dispatch: routes upstream calls to the correct SDK backend."""

from __future__ import annotations

from typing import Any

from core.dependencies import get_settings
from services.anthropic_backend import call_anthropic_from_openai, call_anthropic_native
from services.anthropic_convert import build_anthropic_native_params
from services.openai_backend import call_openai
from services.sdk_clients import SdkClientPool


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
    settings = get_settings()
    provider_slug = target_info.get("provider_slug", "")
    is_anthropic_upstream = provider_slug in settings.ANTHROPIC_NATIVE_SLUGS

    if is_anthropic_upstream:
        if incoming_protocol == "anthropic" and anthropic_request is not None:
            anthropic_params = build_anthropic_native_params(anthropic_request)
            return await call_anthropic_native(
                pool, target_info, anthropic_params, stream=stream, timeout=timeout,
            )
        return await call_anthropic_from_openai(
            pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
        )

    return await call_openai(
        pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
    )
