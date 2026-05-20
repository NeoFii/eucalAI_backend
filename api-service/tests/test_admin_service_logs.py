"""Tests for admin service-logs endpoint (Plan 05-03 Task 3).

Validates:
- test_local_only: GET /api/v1/admin/service-logs?services=api-service returns local RingBuffer entries
- test_partial_on_failure (T-5-08): inference unreachable -> 200 with reachable=False + error
- test_remote_services_only_inference (D-03): _REMOTE_SERVICES has exactly one entry
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
def mock_super_admin_obj():
    from app.model.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 2
    admin.uid = "adm_super1"
    admin.role = AdminRole.SUPER_ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = True
    return admin


@pytest.mark.asyncio
async def test_local_only(mock_super_admin_obj):
    """GET /api/v1/admin/service-logs?services=api-service returns local entries only."""
    from app.core.policies import require_super_admin

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj

    entries = [
        {"seq": 1, "timestamp": "2026-01-01T00:00:01Z", "service": "api-service",
         "level": "INFO", "logger": "test", "event": "evt1"},
        {"seq": 2, "timestamp": "2026-01-01T00:00:02Z", "service": "api-service",
         "level": "INFO", "logger": "test", "event": "evt2"},
        {"seq": 3, "timestamp": "2026-01-01T00:00:03Z", "service": "api-service",
         "level": "WARNING", "logger": "test", "event": "evt3"},
    ]

    mock_buf = MagicMock()
    mock_buf.snapshot = MagicMock(return_value=(entries, 3, 100))

    with patch(
        "app.service.admin.service_logs_service.get_ring_buffer",
        return_value=mock_buf,
    ), patch(
        "app.service.admin.service_logs_service.get_internal_json",
        new_callable=AsyncMock,
    ) as mock_internal:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/admin/service-logs",
                params={"service": "api-service"},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        results = data["results"]
        assert len(results) == 1
        assert results[0]["service"] == "api-service"
        assert results[0]["reachable"] is True
        assert len(results[0]["entries"]) == 3

        # inference-service was NOT fetched
        mock_internal.assert_not_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_partial_on_failure(mock_super_admin_obj):
    """T-5-08: inference unreachable -> 200 with reachable=False + error string."""
    from app.core.policies import require_super_admin
    from app.common.internal import InternalServiceError

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj

    local_entries = [
        {"seq": 1, "timestamp": "2026-01-01T00:00:01Z", "service": "api-service",
         "level": "INFO", "logger": "test", "event": "local_evt"},
    ]

    mock_buf = MagicMock()
    mock_buf.snapshot = MagicMock(return_value=(local_entries, 1, 50))

    async def raise_internal_error(**kwargs):
        raise InternalServiceError(
            "connection refused",
            target_service="inference-service",
            path="/internal/logs",
        )

    with patch(
        "app.service.admin.service_logs_service.get_ring_buffer",
        return_value=mock_buf,
    ), patch(
        "app.service.admin.service_logs_service.get_internal_json",
        side_effect=raise_internal_error,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/service-logs")

        assert resp.status_code == 200
        data = resp.json()["data"]
        results = data["results"]
        assert len(results) == 2

        # Find each service result
        api_result = next(r for r in results if r["service"] == "api-service")
        inference_result = next(r for r in results if r["service"] == "inference-service")

        assert api_result["reachable"] is True
        assert len(api_result["entries"]) == 1

        assert inference_result["reachable"] is False
        assert inference_result["error"] is not None
        assert "connection refused" in inference_result["error"]

    app.dependency_overrides.clear()


def test_remote_services_only_inference():
    """D-03: _REMOTE_SERVICES has exactly one entry — inference-service."""
    from app.service.admin.service_logs_service import _REMOTE_SERVICES

    assert len(_REMOTE_SERVICES) == 1
    assert _REMOTE_SERVICES[0] == ("inference-service", "INFERENCE_SERVICE_URL")
