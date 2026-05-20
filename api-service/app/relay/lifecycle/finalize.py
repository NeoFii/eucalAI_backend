"""Stream finalization — billing settle + call log update (< 200 lines).

Executes in the finally block of stream generators.
Uses asyncio.shield for client_cancelled to protect billing writes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.relay.lifecycle.orchestrator import CallLifecycle

logger = logging.getLogger(__name__)


async def finalize_stream(
    lifecycle: "CallLifecycle",
    collected_content: str,
    stream_usage: dict[str, Any],
    stream_ok: bool,
    abort_reason: str | None,
    t_stream_start: float,
) -> None:
    """Finalize a streaming response — settle billing and update call log.

    Always runs (in finally block). Uses asyncio.shield when client disconnects
    to ensure billing writes complete even if the task is cancelled.
    """
    from app.core.db import get_session_factory
    from app.common.infra.cache import get_cache_redis
    from app.relay.call_log_writer import update_call_log_and_settle

    final_status = 200 if stream_ok else (502 if abort_reason == "stream_error" else 499)
    duration_ms = int((time.monotonic() - lifecycle.t_start) * 1000)

    update_data: dict[str, Any] = {
        "status": final_status,
        "duration_ms": duration_ms,
        "selected_model": lifecycle.selected_model,
    }

    billing_params: dict[str, Any] | None = None

    if stream_ok and stream_usage:
        prompt_tokens = stream_usage.get("prompt_tokens", 0)
        completion_tokens = stream_usage.get("completion_tokens", 0)
        total_tokens = stream_usage.get("total_tokens", 0)

        update_data.update(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        # Compute cost for billing
        config_cache = None
        try:
            from app.relay.dependencies import get_routing_config_cache
            config_cache = get_routing_config_cache()
        except RuntimeError:
            pass

        actual_cost = 0
        if config_cache:
            config = config_cache.load()
            model_prices = config.get("model_prices", {})
            prices = model_prices.get(lifecycle.selected_model, {})
            input_price = prices.get("input", 0)
            output_price = prices.get("output", 0)
            actual_cost = int(
                input_price * prompt_tokens / 1_000_000
                + output_price * completion_tokens / 1_000_000
            )
            actual_cost = max(actual_cost, 1)

        billing_params = {
            "user_id": lifecycle.principal.user_id,
            "pre_consumed": lifecycle.pre_consumed,
            "actual_cost": actual_cost,
            "trusted": lifecycle.trusted,
            "total_tokens": total_tokens,
            "api_key_id": lifecycle.principal.id,
        }

    elif abort_reason == "client_cancelled":
        update_data["error_code"] = "client_aborted"
    elif abort_reason == "stream_error":
        update_data["error_code"] = "upstream_stream_error"

    # Fire-and-forget update + settle
    session_factory = get_session_factory()
    cache_redis = get_cache_redis()

    update_coro = update_call_log_and_settle(
        session_factory, cache_redis,
        lifecycle.request_id, update_data, billing_params,
    )

    if abort_reason == "client_cancelled":
        # Shield from cancellation to ensure billing completes
        task = asyncio.ensure_future(update_coro)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass
    else:
        await update_coro
