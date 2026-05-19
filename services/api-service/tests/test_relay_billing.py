"""Unit tests for relay/billing.py — RelayBillingService (RELAY-06, RELAY-10)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest

from api_service.relay.billing import (
    InsufficientBalanceError,
    RelayBillingService,
)


@pytest.fixture
def mock_redis():
    """AsyncMock for Redis cache layer."""
    r = AsyncMock()
    r.get = AsyncMock()
    r.set = AsyncMock()
    r.decrby = AsyncMock()
    r.incrby = AsyncMock()
    return r


@pytest.fixture
def mock_session_factory():
    """Mock async session factory (context manager)."""
    session = AsyncMock()
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory, session


# ── get_balance tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_redis_hit(mock_redis):
    """Redis GET returns value → return it directly."""
    mock_redis.get.return_value = "5000000"

    balance = await RelayBillingService.get_balance(
        mock_redis, user_id=1, db_session_factory=None
    )
    assert balance == 5_000_000
    mock_redis.get.assert_called_once_with("user:quota:1")


@pytest.mark.asyncio
async def test_get_balance_redis_miss_db_fallback(mock_redis, mock_session_factory):
    """Redis miss → DB query → Redis SET → return balance."""
    mock_redis.get.return_value = None
    factory, session = mock_session_factory

    # Mock the DB query result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 8_000_000
    session.execute = AsyncMock(return_value=mock_result)

    balance = await RelayBillingService.get_balance(
        mock_redis, user_id=1, db_session_factory=factory
    )
    assert balance == 8_000_000
    # Redis SET called for lazy init
    mock_redis.set.assert_called_once_with("user:quota:1", "8000000", ex=300)


# ── estimate_cost tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_estimate_cost_known_model():
    """Known model → formula: output*min(max_tokens,4096)/1M + input*2048/1M."""
    model_prices = {
        "gpt-4": {"input": 2000, "output": 6000},
    }
    # output: 6000 * min(1000, 4096) / 1_000_000 = 6000 * 1000 / 1M = 6
    # input: 2000 * 2048 / 1_000_000 = 4.096
    # total: 10.096 → int = 10
    cost = await RelayBillingService.estimate_cost(model_prices, "gpt-4", 1000)
    assert cost == 10


@pytest.mark.asyncio
async def test_estimate_cost_unknown_model_fallback():
    """Unknown model → return RELAY_BILLING_FALLBACK_COST."""
    from api_service.core.config import settings

    model_prices = {"gpt-4": {"input": 2000, "output": 6000}}
    cost = await RelayBillingService.estimate_cost(model_prices, "unknown-model", 1000)
    assert cost == settings.RELAY_BILLING_FALLBACK_COST


# ── pre_consume tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pre_consume_trusted(mock_redis):
    """Balance > trust_quota → trusted, no Redis DECRBY."""
    amount, trusted = await RelayBillingService.pre_consume(
        mock_redis,
        user_id=1,
        estimated_cost=100_000,
        balance=20_000_000,
        trust_quota=10_000_000,
    )
    assert amount == 0
    assert trusted is True
    mock_redis.decrby.assert_not_called()


@pytest.mark.asyncio
async def test_pre_consume_normal(mock_redis):
    """Balance <= trust_quota → DECRBY, returns (estimated_cost, False)."""
    mock_redis.decrby.return_value = 4_900_000

    amount, trusted = await RelayBillingService.pre_consume(
        mock_redis,
        user_id=1,
        estimated_cost=100_000,
        balance=5_000_000,
        trust_quota=10_000_000,
    )
    assert amount == 100_000
    assert trusted is False
    mock_redis.decrby.assert_called_once_with("user:quota:1", 100_000)


@pytest.mark.asyncio
async def test_pre_consume_insufficient(mock_redis):
    """DECRBY returns negative → rollback INCRBY + raise InsufficientBalanceError."""
    mock_redis.decrby.return_value = -50_000

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await RelayBillingService.pre_consume(
            mock_redis,
            user_id=1,
            estimated_cost=100_000,
            balance=50_000,
            trust_quota=10_000_000,
        )
    assert exc_info.value.balance == 50_000
    assert exc_info.value.required == 100_000
    # Rollback called
    mock_redis.incrby.assert_called_once_with("user:quota:1", 100_000)


# ── settle tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settle_trusted(mock_redis):
    """Trusted → DECRBY actual_cost."""
    await RelayBillingService.settle(
        mock_redis,
        user_id=1,
        pre_consumed=0,
        actual_cost=80_000,
        trusted=True,
    )
    mock_redis.decrby.assert_called_once_with("user:quota:1", 80_000)


@pytest.mark.asyncio
async def test_settle_underpaid(mock_redis):
    """pre_consumed < actual → DECRBY delta."""
    await RelayBillingService.settle(
        mock_redis,
        user_id=1,
        pre_consumed=80_000,
        actual_cost=100_000,
        trusted=False,
    )
    mock_redis.decrby.assert_called_once_with("user:quota:1", 20_000)


@pytest.mark.asyncio
async def test_settle_overpaid(mock_redis):
    """pre_consumed > actual → INCRBY abs(delta)."""
    await RelayBillingService.settle(
        mock_redis,
        user_id=1,
        pre_consumed=100_000,
        actual_cost=60_000,
        trusted=False,
    )
    mock_redis.incrby.assert_called_once_with("user:quota:1", 40_000)


# ── refund tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund(mock_redis):
    """Refund pre_consumed → INCRBY."""
    await RelayBillingService.refund(mock_redis, user_id=1, pre_consumed=100_000)
    mock_redis.incrby.assert_called_once_with("user:quota:1", 100_000)


# ── Redis failure degradation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_down_pre_consume_degrades_to_trusted():
    """Redis raises exception during pre_consume → degrade to trusted mode."""
    mock_redis = AsyncMock()
    mock_redis.decrby = AsyncMock(side_effect=ConnectionError("Redis down"))

    amount, trusted = await RelayBillingService.pre_consume(
        mock_redis,
        user_id=1,
        estimated_cost=100_000,
        balance=5_000_000,
        trust_quota=10_000_000,
    )
    assert amount == 0
    assert trusted is True
