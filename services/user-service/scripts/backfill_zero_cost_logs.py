"""One-time backfill: recalculate cost for api_call_logs that were recorded with cost=0
due to missing routing_slug in supported_models. Creates balance transactions and
deducts from user balance. Idempotent — safe to run multiple times.

Usage:
    cd services/user-service
    uv run python -m scripts.backfill_zero_cost_logs [--dry-run]
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.config import settings
from user_service.db import close_db, create_engine, get_db_context, init_session_factory
from user_service.models.api_call_log import ApiCallLog
from user_service.models.balance_transaction import BalanceTransaction
from user_service.repositories.balance_tx_repository import BalanceTxRepository
from user_service.repositories.user_repository import UserRepository
from user_service.services.usage_stat_service import UsageStatService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv


def _calc_cost(
    non_cached_input: int,
    completion_tokens: int,
    cached_tokens: int,
    input_price: int,
    output_price: int,
    cached_price: int,
) -> int:
    input_cost = non_cached_input * input_price / 1_000_000
    output_cost = completion_tokens * output_price / 1_000_000
    cached_cost = cached_tokens * cached_price / 1_000_000
    total = input_cost + output_cost + cached_cost
    return math.ceil(total) if total > 0 else 0


async def fetch_prices(db: AsyncSession) -> dict[str, dict[str, int]]:
    """Fetch user-facing prices from admin DB via cross-database query."""
    admin_db_name = "eucal_ai_admin"
    rows = (
        await db.execute(
            text(
                f"SELECT routing_slug, price_input_per_m_fen, price_output_per_m_fen, "
                f"price_cached_input_per_m_fen "
                f"FROM {admin_db_name}.supported_models "
                f"WHERE routing_slug IS NOT NULL AND price_input_per_m_fen IS NOT NULL"
            )
        )
    ).all()
    prices: dict[str, dict[str, int]] = {}
    for routing_slug, inp, out, cached in rows:
        prices[routing_slug] = {
            "input": int(inp or 0),
            "output": int(out or 0),
            "cached_input": int(cached or 0),
        }
    return prices


async def backfill() -> None:
    create_engine(settings.DATABASE_URL)
    init_session_factory()

    try:
        async with get_db_context() as db:
            prices = await fetch_prices(db)
            logger.info("Loaded prices for %d models: %s", len(prices), list(prices.keys()))

            logs = list(
                (
                    await db.execute(
                        select(ApiCallLog).where(
                            ApiCallLog.cost == 0,
                            ApiCallLog.status == ApiCallLog.STATUS_SUCCESS,
                            ApiCallLog.prompt_tokens > 0,
                        )
                    )
                )
                .scalars()
                .all()
            )
            logger.info("Found %d call logs with cost=0 to backfill", len(logs))

            if not logs:
                return

            total_cost = 0
            fixed = 0
            affected_hours: set[tuple[int, datetime]] = set()

            for log in logs:
                model = log.selected_model or log.model_name
                model_price = prices.get(model)
                if not model_price:
                    logger.warning("No price for model %s (request_id=%s), skipping", model, log.request_id)
                    continue

                non_cached = max(int(log.prompt_tokens) - int(log.cached_tokens), 0)
                cost = _calc_cost(
                    non_cached,
                    int(log.completion_tokens),
                    int(log.cached_tokens),
                    model_price["input"],
                    model_price["output"],
                    model_price["cached_input"],
                )
                if cost <= 0:
                    continue

                cost_detail = {
                    "non_cached_input_tokens": non_cached,
                    "completion_tokens": int(log.completion_tokens),
                    "cached_tokens": int(log.cached_tokens),
                    "user_prices": model_price,
                    "provider_prices": {"input": 0, "output": 0, "cached_input": 0},
                    "user_cost": cost,
                    "provider_cost": 0,
                }

                logger.info(
                    "%s request_id=%s model=%s tokens=%d/%d cost=%d",
                    "[DRY-RUN]" if DRY_RUN else "[FIX]",
                    log.request_id, model,
                    int(log.prompt_tokens), int(log.completion_tokens), cost,
                )

                if DRY_RUN:
                    total_cost += cost
                    fixed += 1
                    continue

                log.cost = cost
                log.cost_detail = cost_detail

                tx_repo = BalanceTxRepository(db)
                already_billed = await tx_repo.exists_by_ref(
                    tx_type=BalanceTransaction.TYPE_CONSUME,
                    ref_type="api_call",
                    ref_id=log.request_id,
                )
                if not already_billed:
                    user = await UserRepository(db).get_by_id(log.user_id, for_update=True)
                    if user is not None:
                        balance_before = int(user.balance)
                        user.balance = max(int(user.balance) - cost, 0)
                        user.used_amount += cost
                        user.total_requests += 1
                        user.total_tokens += int(log.total_tokens)
                        tx_repo.add(
                            BalanceTransaction(
                                user_id=user.id,
                                type=BalanceTransaction.TYPE_CONSUME,
                                amount=-cost,
                                balance_before=balance_before,
                                balance_after=int(user.balance),
                                ref_type="api_call",
                                ref_id=log.request_id,
                            )
                        )

                stat_hour = log.created_at.replace(minute=0, second=0, microsecond=0)
                affected_hours.add((int(log.user_id), stat_hour))
                total_cost += cost
                fixed += 1

            if not DRY_RUN:
                await db.commit()
                logger.info("Committed %d cost fixes, total cost=%d micro-yuan", fixed, total_cost)

                logger.info("Re-aggregating %d affected hours...", len(affected_hours))
                unique_hours = {h for _, h in affected_hours}
                for stat_hour in sorted(unique_hours):
                    await UsageStatService.aggregate_hour(db, stat_hour)
                await db.commit()
                logger.info("Usage stats re-aggregation complete")
            else:
                logger.info("[DRY-RUN] Would fix %d logs, total cost=%d micro-yuan", fixed, total_cost)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(backfill())
