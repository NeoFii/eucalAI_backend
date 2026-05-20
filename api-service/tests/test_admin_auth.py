"""Plan 05-01 Task 2 — admin auth endpoint tests (ADMIN-01 VALIDATION slots).

Covers:
    T-5-01 test_login_sets_cookies: POST /admin/auth/login returns 200 with
        admin_access_token + admin_refresh_token cookies (HttpOnly, path=/).
    T-5-02 test_lockout: after N consecutive wrong-password attempts the
        admin row's login_locked_until is set and the next attempt raises
        InvalidCredentialsException with the lockout detail.
    T-5-03 test_logout_blacklists: POST /admin/auth/logout calls
        blacklist_token for BOTH the access and refresh JTIs.
    test_refresh_rotates: POST /admin/auth/refresh issues new access AND
        refresh tokens, blacklists the old refresh jti.
    T-5-04 test_change_password_invalidates: POST /admin/auth/change-password
        blacklists active access + refresh JTIs and updates the password hash.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.db import get_db
from app.core.dependencies.admin import get_current_admin
from app.core.policies import require_active_admin
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client(mock_db, mock_admin):
    """ASGI test client with `get_db` overridden to return the mock session
    and `require_active_admin` overridden to return `mock_admin` (skips the
    JWT decode + cookie path for the endpoints that depend on it).
    """
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[require_active_admin] = lambda: mock_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── T-5-01 ─────────────────────────────────────────────────────────────────────


async def test_login_sets_cookies(client: AsyncClient, mock_admin):
    """T-5-01 — successful login emits two HttpOnly cookies at path=/."""
    mock_admin.uid = "adm_test01"
    with patch(
        "app.controller.admin.auth.AdminAuthService.login",
        new=AsyncMock(return_value=(mock_admin, "access-token-stub")),
    ):
        response = await client.post(
            "/api/v1/admin/auth/login",
            json={"email": "admin@example.com", "password": "Secret-1!aA"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["access_token"] == "access-token-stub"

    set_cookie_headers = response.headers.get_list("set-cookie")
    cookies_str = "\n".join(set_cookie_headers)
    assert "admin_access_token=" in cookies_str
    assert "admin_refresh_token=" in cookies_str
    # CONTEXT D-08 — path stays `/` (not /api/v1/admin)
    for header in set_cookie_headers:
        if header.lower().startswith("admin_access_token=") or header.lower().startswith(
            "admin_refresh_token="
        ):
            assert "Path=/" in header
            assert "HttpOnly" in header


# ── T-5-02 ─────────────────────────────────────────────────────────────────────


async def test_lockout(mock_db, mock_admin):
    """T-5-02 — exceeding LOGIN_MAX_FAILURES sets login_locked_until."""
    from datetime import timedelta

    from app.common.core.exceptions import InvalidCredentialsException
    from app.common.utils.timezone import now
    from app.service.admin.auth_service import (
        LOGIN_LOCK_DURATION_HOURS,
        LOGIN_MAX_FAILURES,
        AdminAuthService,
    )

    # Set the failure counter one below the threshold; the next failure
    # MUST flip the locked_until field.
    mock_admin.login_fail_count = LOGIN_MAX_FAILURES - 1
    mock_admin.login_locked_until = None
    # Pretend the password hash check always fails (wrong password).
    mock_repo = MagicMock()
    mock_repo.get_by_email = AsyncMock(return_value=mock_admin)

    before = now()
    with (
        patch(
            "app.service.admin.auth_service.AdminUserRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.service.admin.auth_service.verify_password_async",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.service.admin.auth_service.AdminAuditService.record",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(InvalidCredentialsException) as exc_info:
            await AdminAuthService.login(
                mock_db,
                "admin@example.com",
                "wrong-password",
                "ua",
                "1.2.3.4",
            )

    # login_locked_until is set roughly LOGIN_LOCK_DURATION_HOURS into the future.
    assert mock_admin.login_locked_until is not None
    expected_lock_min = before + timedelta(hours=LOGIN_LOCK_DURATION_HOURS) - timedelta(seconds=5)
    expected_lock_max = before + timedelta(hours=LOGIN_LOCK_DURATION_HOURS) + timedelta(seconds=5)
    assert expected_lock_min <= mock_admin.login_locked_until <= expected_lock_max
    # Detail string carries the lockout duration.
    assert "Too many failed login attempts" in (exc_info.value.detail or "")


# ── T-5-03 ─────────────────────────────────────────────────────────────────────


async def test_logout_blacklists(client: AsyncClient, mock_admin):
    """T-5-03 — logout blacklists BOTH access and refresh JTIs and clears cookies."""
    with (
        patch(
            "app.service.admin.auth_service.blacklist_token",
            new=AsyncMock(return_value=True),
        ) as mock_blacklist,
        patch(
            "app.service.admin.auth_service.get_token_jti",
            side_effect=lambda token: f"jti-{token}",
        ),
        patch(
            "app.service.admin.auth_service._remaining_ttl",
            return_value=600,
        ),
    ):
        response = await client.post(
            "/api/v1/admin/auth/logout",
            cookies={
                "admin_access_token": "access-cookie",
                "admin_refresh_token": "refresh-cookie",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200

    # blacklist_token was awaited TWICE — once for access jti, once for refresh jti.
    assert mock_blacklist.await_count == 2
    awaited_args = {call.args[0] for call in mock_blacklist.await_args_list}
    assert "jti-access-cookie" in awaited_args
    assert "jti-refresh-cookie" in awaited_args

    set_cookie_headers = response.headers.get_list("set-cookie")
    cookies_str = "\n".join(set_cookie_headers)
    # FastAPI delete_cookie sends an empty value with Max-Age=0.
    assert "admin_access_token=" in cookies_str
    assert "admin_refresh_token=" in cookies_str


# ── refresh rotation ───────────────────────────────────────────────────────────


async def test_refresh_rotates(client: AsyncClient):
    """POST /admin/auth/refresh rotates both tokens and sets new cookies."""
    with patch(
        "app.controller.admin.auth.AdminAuthService.refresh_access_token",
        new=AsyncMock(return_value=("new-access-token", "new-refresh-token")),
    ) as mock_refresh:
        response = await client.post(
            "/api/v1/admin/auth/refresh",
            cookies={"admin_refresh_token": "old-refresh-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["access_token"] == "new-access-token"
    mock_refresh.assert_awaited_once()
    set_cookie_headers = response.headers.get_list("set-cookie")
    cookies_str = "\n".join(set_cookie_headers)
    assert "admin_access_token=new-access-token" in cookies_str
    assert "admin_refresh_token=new-refresh-token" in cookies_str


# ── T-5-04 ─────────────────────────────────────────────────────────────────────


async def test_change_password_invalidates(client: AsyncClient, mock_admin):
    """T-5-04 — change_password updates the hash AND blacklists active JTIs."""
    new_hash = "$2b$12$NEWHASHRESULT"
    with (
        patch(
            "app.service.admin.auth_service.verify_password_async",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.service.admin.auth_service.check_password_strength",
            return_value=(True, ""),
        ),
        patch(
            "app.service.admin.auth_service.hash_password_async",
            new=AsyncMock(return_value=new_hash),
        ),
        patch(
            "app.service.admin.auth_service.AdminAuditService.record",
            new=AsyncMock(),
        ),
        patch(
            "app.service.admin.auth_service.blacklist_token",
            new=AsyncMock(return_value=True),
        ) as mock_blacklist,
        patch(
            "app.service.admin.auth_service.get_token_jti",
            side_effect=lambda token: f"jti-{token}",
        ),
        patch(
            "app.service.admin.auth_service._remaining_ttl",
            return_value=600,
        ),
    ):
        response = await client.post(
            "/api/v1/admin/auth/change-password",
            json={
                "old_password": "OldSecret-1!aA",
                "new_password": "NewSecret-2!bB",
            },
            cookies={
                "admin_access_token": "access-cookie",
                "admin_refresh_token": "refresh-cookie",
            },
        )

    assert response.status_code == 200
    assert mock_admin.password_hash == new_hash
    # Both jtis blacklisted.
    assert mock_blacklist.await_count == 2
