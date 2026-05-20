"""Fire-and-forget call log writer — two-step DB write (D-14~D-17).

Step 1: create_call_log — asyncio.create_task writes initial pending record.
Step 2: update_call_log_and_settle — asyncio.create_task updates record + settles billing.

Both steps use independent sessions (D-15) and never block the request flow.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import update

from app.model.api_call_log import ApiCallLog

logger = logging.getLogger(__name__)


async def create_call_log(session_factory, log_data: dict[str, Any]) -> None:
    """Fire-and-forget: create initial call log record (status=pending).

    Uses asyncio.create_task so the request is not blocked (D-14).
    """
    asyncio.create_task(_write_call_log_create(session_factory, log_data))


async def _write_call_log_create(session_factory, log_data: dict[str, Any]) -> None:
    """Independent session write — fire-and-forget (D-15)."""
    try:
        async with session_factory() as session:
            log = ApiCallLog(**log_data)
            session.add(log)
            await session.commit()
    except Exception as exc:
        logger.warning("call_log create failed: %s", exc)


async def update_call_log_and_settle(
    session_factory,
    cache_redis,
    request_id: str,
    update_data: dict[str, Any],
    billing_params: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget: update call log + settle billing in same task (D-17).

    Uses asyncio.create_task so the response is not blocked.
    """
    asyncio.create_task(
        _write_call_log_update_and_settle(
            session_factory, cache_redis, request_id, update_data, billing_params
        )
    )


async def _write_call_log_update_and_settle(
    session_factory,
    cache_redis,
    request_id: str,
    update_data: dict[str, Any],
    billing_params: dict[str, Any] | None,
    max_retries: int = 3,
) -> None:
    """Update call log then settle billing — sequential in same task (D-17).

    Billing settle retries up to 3 times on failure (D-16).
    """
    # 1. Update call log record
    try:
        async with session_factory() as session:
            await session.execute(
                update(ApiCallLog)
                .where(ApiCallLog.request_id == request_id)
                .values(**update_data)
            )
            await session.commit()
    except Exception as exc:
        logger.warning("call_log update failed for request_id=%s: %s", request_id, exc)

    # 2. Settle billing (retry up to max_retries times, D-16)
    if billing_params is None:
        return

    from app.relay.billing import RelayBillingService
    from app.service.balance_service import BalanceService

    # 2a. Redis settle (adjust pre-consumed vs actual)
    for attempt in range(max_retries):
        try:
            await RelayBillingService.settle(
                cache_redis=cache_redis,
                user_id=billing_params["user_id"],
                pre_consumed=billing_params["pre_consumed"],
                actual_cost=billing_params["actual_cost"],
                trusted=billing_params["trusted"],
            )
            break
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "billing settle failed after %d retries for request_id=%s: %s",
                    max_retries, request_id, exc,
                )
            else:
                await asyncio.sleep(0.1 * (attempt + 1))

    # 2b. DB persist (BalanceService.consume_for_call_log)
    for attempt in range(max_retries):
        try:
            async with session_factory() as session:
                await BalanceService.consume_for_call_log(
                    db=session,
                    user_id=billing_params["user_id"],
                    request_id=request_id,
                    cost=billing_params["actual_cost"],
                    total_tokens=billing_params.get("total_tokens", 0),
                    api_key_id=billing_params.get("api_key_id"),
                )
                await session.commit()
            break
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "billing DB persist failed after %d retries for request_id=%s: %s",
                    max_retries, request_id, exc,
                )
            else:
                await asyncio.sleep(0.1 * (attempt + 1))


__all__ = ["create_call_log", "update_call_log_and_settle"]
