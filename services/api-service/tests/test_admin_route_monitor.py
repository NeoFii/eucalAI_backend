"""Tests for admin route-monitor endpoints (Plan 05-03 Task 2).

Validates:
- test_list: GET /api/v1/admin/route-monitor/requests resolves user_uid
- test_compare: GET /api/v1/admin/route-monitor/compare/{id} uses find_same_input_siblings
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api_service.main import app


@pytest.fixture
def mock_admin_obj():
    from api_service.models.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 1
    admin.uid = "adm_test01"
    admin.role = AdminRole.ADMIN
    admin.status = AdminStatus.ACTIVE
    return admin


@pytest.fixture
def mock_super_admin_obj():
    from api_service.models.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 2
    admin.uid = "adm_super1"
    admin.role = AdminRole.SUPER_ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = True
    return admin


@pytest.mark.asyncio
async def test_list(mock_admin_obj):
    """GET /api/v1/admin/route-monitor/requests resolves user_uid to user_id."""
    from api_service.core.policies import require_active_admin
    from api_service.core.db import get_db

    mock_db = AsyncMock()

    app.dependency_overrides[require_active_admin] = lambda: mock_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_user = MagicMock()
    mock_user.id = 42
    mock_user.uid = "u_xxx"

    with patch(
        "api_service.services.admin.route_monitor_service.UserRepository"
    ) as MockUserRepo, patch(
        "api_service.services.admin.route_monitor_service.CallLogRepository"
    ) as MockCallLogRepo:
        user_repo = MagicMock()
        user_repo.get_by_uid = AsyncMock(return_value=mock_user)
        MockUserRepo.return_value = user_repo

        call_log_repo = MagicMock()
        call_log_repo.list_requests = AsyncMock(return_value=([], 0))
        MockCallLogRepo.return_value = call_log_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/admin/route-monitor/requests",
                params={"page": 1, "page_size": 20, "user_uid": "u_xxx"},
            )

        assert resp.status_code == 200
        # UserRepository resolved uid -> user_id
        user_repo.get_by_uid.assert_awaited_once_with("u_xxx")
        # CallLogRepository was called with resolved user_id
        call_log_repo.list_requests.assert_awaited_once()
        call_kwargs = call_log_repo.list_requests.call_args[1]
        assert call_kwargs["user_id"] == 42

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_compare(mock_super_admin_obj):
    """GET /api/v1/admin/route-monitor/compare/{id} uses find_same_input_siblings."""
    from api_service.core.policies import require_super_admin
    from api_service.core.db import get_db

    mock_db = AsyncMock()

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_target = MagicMock()
    mock_target.input_hash = "abc123"
    mock_target.id = 1
    mock_target.request_id = "req_001"
    mock_target.selected_model = "gpt-4"
    mock_target.routing_tier = 1
    mock_target.total_score_0_10 = None
    mock_target.score_source = None
    mock_target.status = 200
    mock_target.duration_ms = 100
    mock_target.upstream_latency_ms = 80
    mock_target.cost = 500
    mock_target.config_version = 1
    mock_target.inference_config_version = 1
    mock_target.created_at = "2026-01-01T00:00:00"

    with patch(
        "api_service.services.admin.route_monitor_service.CallLogRepository"
    ) as MockCallLogRepo:
        call_log_repo = MagicMock()
        call_log_repo.find_same_input_siblings = AsyncMock(
            return_value=(mock_target, [])
        )
        MockCallLogRepo.return_value = call_log_repo

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/route-monitor/compare/req_001")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["input_hash"] == "abc123"
        # find_same_input_siblings was called
        call_log_repo.find_same_input_siblings.assert_awaited_once()

    app.dependency_overrides.clear()
