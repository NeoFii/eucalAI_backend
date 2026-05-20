"""Tests for admin user-management endpoints (Plan 05-03 Task 1).

Validates:
- T-5-06: test_list_no_http — no httpx calls during admin user list
- test_topup_atomic_with_audit — topup + audit + commit atomicity
- T-5-07: test_reset_password_revokes_sessions — sessions revoked after reset
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
def mock_user_obj():
    user = MagicMock()
    user.id = 42
    user.uid = "u_test42"
    user.email = "user42@example.com"
    user.status = 1
    user.email_verified_at = None
    user.last_login_at = None
    user.balance = 1000000
    user.rpm_limit = None
    user.created_at = "2026-01-01T00:00:00"
    user.updated_at = None
    user.password_hash = "$2b$12$dummyhash"
    return user


@pytest.fixture
def mock_super_admin_obj():
    from app.model.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 2
    admin.uid = "adm_super1"
    admin.email = "super@example.com"
    admin.name = "Super Admin"
    admin.role = AdminRole.SUPER_ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = True
    return admin


@pytest.mark.asyncio
async def test_list_no_http(mock_user_obj, mock_super_admin_obj):
    """T-5-06: GET /api/v1/admin/users uses UserRepository directly, zero httpx calls."""
    from app.core.policies import require_active_admin
    from app.core.db import get_db

    mock_db = AsyncMock()

    app.dependency_overrides[require_active_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch(
        "app.service.admin.admin_user_service.UserRepository"
    ) as MockRepo:
        repo_instance = MagicMock()
        repo_instance.list_users = AsyncMock(return_value=([mock_user_obj], 1))
        MockRepo.return_value = repo_instance

        with patch("httpx.AsyncClient") as MockHttpx:
            mock_httpx_instance = AsyncMock()
            MockHttpx.return_value = mock_httpx_instance

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/admin/users?page=1&page_size=20")

            assert resp.status_code == 200
            # Assert UserRepository was called
            repo_instance.list_users.assert_awaited_once()
            # Assert no httpx calls were made
            mock_httpx_instance.get.assert_not_called()
            mock_httpx_instance.request.assert_not_called()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_topup_atomic_with_audit(mock_user_obj, mock_super_admin_obj):
    """POST /api/v1/admin/users/{uid}/topup: BalanceService.topup + audit + commit."""
    from app.core.policies import require_super_admin
    from app.core.db import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch(
        "app.service.admin.admin_user_service.UserRepository"
    ) as MockRepo, patch(
        "app.service.admin.admin_user_service.BalanceService"
    ) as MockBalance, patch(
        "app.controller.admin.users.AdminAuditService"
    ) as MockAudit:
        repo_instance = MagicMock()
        repo_instance.get_by_uid = AsyncMock(return_value=mock_user_obj)
        MockRepo.return_value = repo_instance

        MockBalance.topup = AsyncMock()
        MockAudit.record = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/admin/users/{mock_user_obj.uid}/topup",
                json={"amount": 1000000, "remark": "test topup"},
            )

        assert resp.status_code == 200
        # BalanceService.topup was called
        MockBalance.topup.assert_awaited_once()
        # Audit was recorded
        MockAudit.record.assert_awaited_once()
        # db.commit was called (atomicity)
        mock_db.commit.assert_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reset_password_revokes_sessions(mock_user_obj, mock_super_admin_obj):
    """T-5-07: POST /api/v1/admin/users/{uid}/reset-password revokes all sessions."""
    from app.core.policies import require_super_admin
    from app.core.db import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch(
        "app.service.admin.admin_user_service.UserRepository"
    ) as MockRepo, patch(
        "app.service.admin.admin_user_service.hash_password_async",
        new=AsyncMock(return_value="$2b$12$newhash"),
    ), patch(
        "app.service.admin.admin_user_service.AuthService"
    ) as MockAuth, patch(
        "app.controller.admin.users.AdminAuditService"
    ) as MockAudit:
        repo_instance = MagicMock()
        repo_instance.get_by_uid = AsyncMock(return_value=mock_user_obj)
        MockRepo.return_value = repo_instance

        MockAuth.revoke_all_user_sessions = AsyncMock()
        MockAudit.record = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/admin/users/{mock_user_obj.uid}/reset-password",
                json={"new_password": "NewStr0ng!Pass123"},
            )

        assert resp.status_code == 200
        # Sessions were revoked
        MockAuth.revoke_all_user_sessions.assert_awaited_once_with(mock_db, mock_user_obj.id)
        # Password was updated
        assert mock_user_obj.password_hash == "$2b$12$newhash"

    app.dependency_overrides.clear()
