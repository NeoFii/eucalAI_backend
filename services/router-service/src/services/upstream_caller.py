"""Shared upstream call orchestration with channel retry and tier descent."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from core.dependencies import get_channel_selector, get_config_manager, get_rate_limiter, get_sdk_client_pool
from services.retry_policy import extract_status_code, should_retry
from services.routing import resolve_target
from services.upstream_dispatch import dispatch

_logger = logging.getLogger("router_service")


@dataclass
class UpstreamCallFailed(Exception):
    """Raised when all upstream attempts are exhausted."""
    exc: Exception
    target_info: dict[str, Any]
    upstream_latency_ms: float


async def upstream_call_with_retry(
    *,
    selected_model: str,
    messages: list[dict[str, Any]],
    target_info: dict[str, Any],
    forward_payload: dict[str, Any],
    is_stream: bool,
    max_retries: int,
    timeout: float = 45.0,
    incoming_protocol: str = "openai",
    anthropic_request: Any | None = None,
) -> tuple[Any, dict[str, Any], float]:
    """Execute upstream call with channel retry and tier descent.

    Returns (response, final_target_info, upstream_latency_ms).
    Raises UpstreamCallFailed if all attempts are exhausted.
    """
    channel_slug = target_info.get("channel_slug")
    tried_slugs: set[str] = set()
    t_upstream = time.monotonic()

    for attempt in range(max_retries + 1):
        if channel_slug:
            tried_slugs.add(channel_slug)
        try:
            pool = get_sdk_client_pool()
            response = await dispatch(
                pool, target_info,
                messages=messages,
                forward_payload=forward_payload,
                stream=is_stream,
                timeout=timeout,
                incoming_protocol=incoming_protocol,
                anthropic_request=anthropic_request,
            )
            if channel_slug:
                get_channel_selector().report_success(channel_slug)
            account_id = target_info.get("pool_account_id")
            if account_id is not None:
                limiter = get_rate_limiter()
                if limiter is not None:
                    await limiter.check_account(account_id, target_info.get("rpm_limit"))
            upstream_latency_ms = (time.monotonic() - t_upstream) * 1000
            return response, target_info, upstream_latency_ms
        except Exception as exc:
            status_code = extract_status_code(exc)
            if channel_slug:
                get_channel_selector().report_failure(channel_slug)
            if attempt < max_retries and should_retry(exc, status_code):
                config = get_config_manager().load()
                try:
                    target_info = await resolve_target(
                        selected_model, config,
                        excluded_slugs=frozenset(tried_slugs),
                        retry_tier=attempt + 1,
                    )
                    channel_slug = target_info.get("channel_slug")
                    t_upstream = time.monotonic()
                    _logger.warning(
                        "retrying upstream call (attempt %d/%d) for %s, switching to %s",
                        attempt + 1, max_retries,
                        selected_model, channel_slug or target_info["provider_slug"],
                    )
                    continue
                except Exception:
                    pass
            raise UpstreamCallFailed(
                exc=exc,
                target_info=target_info,
                upstream_latency_ms=(time.monotonic() - t_upstream) * 1000,
            ) from exc

    raise RuntimeError("upstream retry loop exited unexpectedly")
