"""Tests for admin dashboard endpoints (Plan 05-03 Task 2).

Validates:
- test_summary_no_http: GET /api/v1/admin/dashboard/summary uses repos directly
- test_rpm_trend_bucketing: RPM trend returns bucketed data
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_admin_obj():
    from app.model.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 1
    admin.uid = "adm_test01"
    admin.role = AdminRole.ADMIN
    admin.status = AdminStatus.ACTIVE
    return admin


@pytest.mark.asyncio
async def test_summary_no_http(mock_admin_obj):
    """GET /api/v1/admin/dashboard/summary uses repos directly, zero httpx calls."""
    from app.core.policies import require_active_admin
    from app.core.db import get_db

    mock_db = AsyncMock()

    app.dependency_overrides[require_active_admin] = lambda: mock_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    platform_summary = {
        "total_requests": 100,
        "requests_today": 10,
        "total_revenue": 5000,
        "revenue_today": 500,
        "total_provider_cost": 3000,
        "provider_cost_today": 300,
        "requests_in_range": 50,
        "revenue_in_range": 2500,
        "provider_cost_in_range": 1500,
    }

    with patch(
        "app.service.admin.dashboard_service.UserRepository"
    ) as MockUserRepo, patch(
        "app.service.admin.dashboard_service.BillingRepository"
    ) as MockBillingRepo:
        user_repo = MagicMock()
        user_repo.count_all = AsyncMock(return_value=42)
        user_repo.count_since = AsyncMock(return_value=3)
        user_repo.count_in_range = AsyncMock(return_value=15)
        MockUserRepo.return_value = user_repo

        billing_repo = MagicMock()
        billing_repo.stat_get_platform_summary = AsyncMock(return_value=platform_summary)
        MockBillingRepo.return_value = billing_repo

        with patch("httpx.AsyncClient") as MockHttpx:
            mock_httpx_instance = AsyncMock()
            MockHttpx.return_value = mock_httpx_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/dashboard/summary")

            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["total_users"] == 42
            assert data["total_requests"] == 100
            # No httpx calls
            mock_httpx_instance.get.assert_not_called()

        # BillingRepository was called
        billing_repo.stat_get_platform_summary.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rpm_trend_bucketing(mock_admin_obj):
    """GET /api/v1/admin/dashboard/rpm-trend returns bucketed data."""
    from app.core.policies import require_active_admin
    from app.core.db import get_db

    mock_db = AsyncMock()

    app.dependency_overrides[require_active_admin] = lambda: mock_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    trend_points = [
        {"bucket_start": "2026-01-01T00:00:00", "request_count": 10, "rpm": 10.0},
        {"bucket_start": "2026-01-01T00:01:00", "request_count": 15, "rpm": 15.0},
    ]

    with patch(
        "app.service.admin.dashboard_service.BillingRepository"
    ) as MockBillingRepo:
        billing_repo = MagicMock()
        billing_repo.stat_get_rpm_trend = AsyncMock(return_value=trend_points)
        MockBillingRepo.return_value = billing_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/admin/dashboard/rpm-trend",
                params={
                    "start": "2026-01-01T00:00:00",
                    "end": "2026-01-01T01:00:00",
                    "bucket_seconds": 60,
                },
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bucket_seconds"] == 60
        assert len(data["points"]) == 2

        # Verify bucket spacing is 60s
        billing_repo.stat_get_rpm_trend.assert_awaited_once()
        call_kwargs = billing_repo.stat_get_rpm_trend.call_args[1]
        assert call_kwargs["bucket_seconds"] == 60

    app.dependency_overrides.clear()
