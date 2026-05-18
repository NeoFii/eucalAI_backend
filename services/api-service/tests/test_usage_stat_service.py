"""Unit tests for UsageStatService granularity / analytics window (USER-04, T-04-17).

T-04-17: get_usage_analytics granularity flips at the 48-hour boundary.
- start..end <= 48h → granularity = "hour"
- start..end >  48h → granularity = "day"
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.services.usage_stat_service import UsageStatService  # noqa: E402


def test_build_window_8h_uses_hour_granularity():
    """_build_usage_analytics_window('8h', now) → granularity='hour'."""
    reference = datetime(2026, 5, 19, 12, 30, 45)
    start, end, granularity = UsageStatService._build_usage_analytics_window("8h", reference)

    assert granularity == "hour"
    assert (end - start) == timedelta(hours=8)


def test_build_window_24h_uses_hour_granularity():
    """_build_usage_analytics_window('24h', now) → granularity='hour'."""
    reference = datetime(2026, 5, 19, 12, 30, 45)
    _start, _end, granularity = UsageStatService._build_usage_analytics_window("24h", reference)
    assert granularity == "hour"


def test_build_window_30d_uses_day_granularity():
    """_build_usage_analytics_window('30d', now) → granularity='day'."""
    reference = datetime(2026, 5, 19, 12, 30, 45)
    _start, _end, granularity = UsageStatService._build_usage_analytics_window("30d", reference)
    assert granularity == "day"


def test_build_window_7d_uses_day_granularity():
    """_build_usage_analytics_window('7d', now) → granularity='day'."""
    reference = datetime(2026, 5, 19, 12, 30, 45)
    _start, _end, granularity = UsageStatService._build_usage_analytics_window("7d", reference)
    assert granularity == "day"


@pytest.mark.asyncio
@patch("api_service.services.usage_stat_service.BillingRepository")
async def test_granularity_switch_at_48h(mock_billing_cls):
    """T-04-17 — explicit start..end:
    - delta == 48h → granularity = "hour"
    - delta == 49h → granularity = "day"
    """
    db = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.stat_list_analytics_logs = AsyncMock(return_value=[])
    mock_billing_cls.return_value = mock_repo

    t0 = datetime(2026, 5, 1, 0, 0, 0)

    # Exactly 48 hours → "hour" (boundary inclusive per source: end - start <= 48h)
    result = await UsageStatService.get_usage_analytics(
        db, user_id=1, start=t0, end=t0 + timedelta(hours=48),
    )
    assert result.granularity == "hour", (
        f"<= 48h → 'hour', got {result.granularity!r}"
    )

    # 49 hours → "day"
    result = await UsageStatService.get_usage_analytics(
        db, user_id=1, start=t0, end=t0 + timedelta(hours=49),
    )
    assert result.granularity == "day", (
        f"> 48h → 'day', got {result.granularity!r}"
    )
