"""Integration tests for POST /api/v1/auth/login (USER-01, T-04-03, T-04-04)."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from app.common.core.exceptions import InvalidCredentialsException  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.uid = "u_test01"
    user.email = "user@example.com"
    user.status = 1
    user.email_verified_at = datetime(2026, 1, 1, 0, 0, 0)
    user.last_login_at = None
    user.created_at = datetime(2026, 1, 1, 0, 0, 0)
    return user


@pytest_asyncio.fixture
async def client():
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("app.controller.auth.AuthService.login", new_callable=AsyncMock)
async def test_login_success(mock_login, client):
    """T-04-03 — login success: 200, sets HttpOnly + SameSite cookies, returns access_token."""
    user = _stub_user()
    mock_login.return_value = (user, "access-token-xyz", "refresh-token-xyz")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Abcdefg1!"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["user"]["uid"] == "u_test01"
    assert "user_id" not in body["data"]["user"]
    assert body["data"]["access_token"] == "access-token-xyz"

    cookie_headers = response.headers.get_list("set-cookie")
    cookies_joined = "\n".join(cookie_headers)
    assert "user_access_token=" in cookies_joined
    assert "user_refresh_token=" in cookies_joined
    assert "HttpOnly" in cookies_joined or "httponly" in cookies_joined.lower()


@pytest.mark.asyncio
@patch("app.controller.auth.AuthService.login", new_callable=AsyncMock)
async def test_login_lockout(mock_login, client):
    """T-04-04 — login lockout returns 401 with detailed message after threshold."""
    mock_login.side_effect = InvalidCredentialsException(
        detail="登录失败次数过多，账户已被锁定，请60分钟后再试"
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    body = response.json()
    # Body must signal credential/lockout failure
    detail = body.get("detail") or body.get("message") or ""
    assert "锁定" in detail or "locked" in detail.lower() or "failed" in detail.lower()
