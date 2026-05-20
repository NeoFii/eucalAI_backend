"""RelayBillingService — pre-consume / settle / refund lifecycle (RELAY-06, RELAY-10).

Implements the new-api BillingSession pattern adapted for Python + Redis DECRBY.
All Redis operations are fail-open (D-06): on error, degrades to trusted mode.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    """Raised when user balance is insufficient for pre-consume."""

    def __init__(self, balance: int, required: int) -> None:
        self.balance = balance
        self.required = required
        super().__init__(
            f"Insufficient balance: have {balance}, need {required}"
        )


class RelayBillingService:
    """Encapsulates pre-consume -> settle -> refund lifecycle.

    All methods are @staticmethod with explicit cache_redis parameter.
    Redis is the hot-path source for balance; DB is the persistence layer.
    """

    @staticmethod
    async def get_balance(
        cache_redis: aioredis.Redis,
        user_id: int,
        db_session_factory,
    ) -> int:
        """Get user balance from Redis (hot) or DB (fallback, lazy init).

        Returns balance in micro-units.
        """
        # Try Redis first
        try:
            val = await cache_redis.get(f"user:quota:{user_id}")
            if val is not None:
                return int(val)
        except Exception:
            logger.debug("Redis unavailable for balance lookup, falling back to DB")

        # Redis miss or error → DB fallback (lazy init)
        from app.model import User
        from sqlalchemy import select

        async with db_session_factory() as session:
            result = await session.execute(
                select(User.balance).where(User.id == user_id)
            )
            row = result.scalar_one_or_none()
            balance = int(row) if row is not None else 0

        # Write-back to Redis (best-effort, 300s TTL for lazy init)
        try:
            await cache_redis.set(f"user:quota:{user_id}", str(balance), ex=300)
        except Exception:
            logger.debug("Redis write-back failed for user:quota:%d", user_id)

        return balance

    @staticmethod
    async def estimate_cost(
        model_prices: dict,
        model: str,
        max_tokens: int | None,
    ) -> int:
        """Estimate pre-consume cost based on model prices (D-05).

        Formula: output_price * min(max_tokens, 4096) / 1M + input_price * 2048 / 1M
        Returns int in micro-units.
        """
        prices = model_prices.get(model)
        if prices is None:
            return settings.RELAY_BILLING_FALLBACK_COST

        output_price = prices.get("output", 0)
        input_price = prices.get("input", 0)
        effective_max_tokens = min(max_tokens or 4096, 4096)

        cost = (
            output_price * effective_max_tokens / 1_000_000
            + input_price * 2048 / 1_000_000
        )
        return max(int(cost), 1)  # At least 1 micro-unit

    @staticmethod
    async def pre_consume(
        cache_redis: aioredis.Redis,
        user_id: int,
        estimated_cost: int,
        balance: int,
        trust_quota: int,
    ) -> tuple[int, bool]:
        """Pre-consume quota. Returns (pre_consumed_amount, is_trusted).

        If balance > trust_quota: skip pre-consume (D-04), return (0, True).
        Otherwise: DECRBY user:quota:{user_id} by estimated_cost.
        On Redis error: degrade to trusted mode (D-06).
        """
        if balance > trust_quota:
            return 0, True

        try:
            new_balance = await cache_redis.decrby(
                f"user:quota:{user_id}", estimated_cost
            )
            if new_balance < 0:
                # Rollback: insufficient balance
                await cache_redis.incrby(f"user:quota:{user_id}", estimated_cost)
                raise InsufficientBalanceError(balance=balance, required=estimated_cost)
            return estimated_cost, False
        except InsufficientBalanceError:
            raise
        except Exception:
            # Redis down → degrade to trusted mode (D-06)
            logger.warning(
                "Redis unavailable for pre-consume (user=%d), degrading to trusted mode",
                user_id,
            )
            return 0, True

    @staticmethod
    async def settle(
        cache_redis: aioredis.Redis,
        user_id: int,
        pre_consumed: int,
        actual_cost: int,
        trusted: bool,
    ) -> None:
        """Settle: adjust delta between pre-consumed and actual cost.

        If trusted: DECRBY actual_cost (was not pre-consumed).
        Else: compute delta and adjust.
        On Redis error: log warning (DB persist handles via create_task).
        """
        try:
            if trusted:
                # Was not pre-consumed, deduct actual now
                await cache_redis.decrby(f"user:quota:{user_id}", actual_cost)
            else:
                delta = actual_cost - pre_consumed
                if delta > 0:
                    await cache_redis.decrby(f"user:quota:{user_id}", delta)
                elif delta < 0:
                    await cache_redis.incrby(f"user:quota:{user_id}", -delta)
                # delta == 0: no adjustment needed
        except Exception:
            logger.warning(
                "Redis settle failed (user=%d, pre=%d, actual=%d), "
                "DB persist will reconcile",
                user_id,
                pre_consumed,
                actual_cost,
            )

    @staticmethod
    async def refund(
        cache_redis: aioredis.Redis,
        user_id: int,
        pre_consumed: int,
    ) -> None:
        """Refund pre-consumed amount on request failure.

        On Redis error: log warning.
        """
        if pre_consumed <= 0:
            return
        try:
            await cache_redis.incrby(f"user:quota:{user_id}", pre_consumed)
        except Exception:
            logger.warning(
                "Redis refund failed (user=%d, amount=%d)", user_id, pre_consumed
            )


__all__ = ["InsufficientBalanceError", "RelayBillingService"]
