"""Tests for relay/call_log_writer.py — fire-and-forget DB write + billing settle."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.relay.call_log_writer import (
    _write_call_log_create,
    _write_call_log_update_and_settle,
)


@asynccontextmanager
async def _mock_session_factory():
    """Simulate an async session context manager."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    yield session


def _make_session_factory():
    """Return a callable that produces the mock session context manager."""
    return _mock_session_factory


class TestCreateCallLog:
    """Tests for _write_call_log_create."""

    @pytest.mark.asyncio
    async def test_create_call_log_writes_to_db(self):
        """test_create_call_log_writes_to_db: verify session.add called with ApiCallLog."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def factory():
            yield session

        log_data = {"request_id": "req-001", "user_id": 1, "model_name": "gpt-4"}

        with patch("app.relay.call_log_writer.ApiCallLog") as MockLog:
            MockLog.return_value = MagicMock()
            await _write_call_log_create(factory, log_data)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_call_log_failure_logs_warning(self, caplog):
        """test_create_call_log_failure_logs_warning: commit raises, verify warning logged."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock(side_effect=Exception("DB connection lost"))

        @asynccontextmanager
        async def factory():
            yield session

        log_data = {"request_id": "req-002", "user_id": 1, "model_name": "gpt-4"}

        with caplog.at_level(logging.WARNING):
            with patch("app.relay.call_log_writer.ApiCallLog") as MockLog:
                MockLog.return_value = MagicMock()
                await _write_call_log_create(factory, log_data)

        assert "call_log create failed" in caplog.text


class TestUpdateAndSettle:
    """Tests for _write_call_log_update_and_settle."""

    @pytest.mark.asyncio
    async def test_update_and_settle_updates_then_settles(self):
        """test_update_and_settle_updates_then_settles: verify both called in order."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def factory():
            yield session

        cache_redis = AsyncMock()
        billing_params = {
            "user_id": 1,
            "pre_consumed": 100,
            "actual_cost": 80,
            "trusted": False,
            "total_tokens": 500,
            "api_key_id": 10,
        }

        with patch("app.relay.billing.RelayBillingService.settle", new_callable=AsyncMock) as mock_settle:
            with patch("app.service.balance_service.BalanceService.consume_for_call_log", new_callable=AsyncMock) as mock_consume:
                await _write_call_log_update_and_settle(
                    factory, cache_redis, "req-003",
                    {"status": 200, "total_tokens": 500},
                    billing_params,
                )

        # Verify update was executed
        assert session.execute.await_count >= 1
        # Verify billing settle was called
        mock_settle.assert_awaited_once()
        # Verify DB persist was called
        mock_consume.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_and_settle_billing_retry(self):
        """test_update_and_settle_billing_retry: settle fails twice then succeeds."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def factory():
            yield session

        cache_redis = AsyncMock()
        billing_params = {
            "user_id": 1,
            "pre_consumed": 100,
            "actual_cost": 80,
            "trusted": False,
            "total_tokens": 500,
            "api_key_id": 10,
        }

        call_count = 0

        async def settle_with_failures(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Redis timeout")

        with patch("app.relay.billing.RelayBillingService.settle", new_callable=AsyncMock, side_effect=settle_with_failures) as mock_settle:
            with patch("app.service.balance_service.BalanceService.consume_for_call_log", new_callable=AsyncMock):
                await _write_call_log_update_and_settle(
                    factory, cache_redis, "req-004",
                    {"status": 200},
                    billing_params,
                )

        # settle was called 3 times (2 failures + 1 success)
        assert mock_settle.await_count == 3

    @pytest.mark.asyncio
    async def test_update_and_settle_billing_all_retries_fail(self, caplog):
        """test_update_and_settle_billing_all_retries_fail: 3 failures, verify error logged."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def factory():
            yield session

        cache_redis = AsyncMock()
        billing_params = {
            "user_id": 1,
            "pre_consumed": 100,
            "actual_cost": 80,
            "trusted": False,
            "total_tokens": 500,
            "api_key_id": 10,
        }

        with caplog.at_level(logging.ERROR):
            with patch("app.relay.billing.RelayBillingService.settle", new_callable=AsyncMock, side_effect=Exception("Redis down")):
                with patch("app.service.balance_service.BalanceService.consume_for_call_log", new_callable=AsyncMock, side_effect=Exception("DB down")):
                    await _write_call_log_update_and_settle(
                        factory, cache_redis, "req-005",
                        {"status": 200},
                        billing_params,
                    )

        assert "billing settle failed after 3 retries" in caplog.text
