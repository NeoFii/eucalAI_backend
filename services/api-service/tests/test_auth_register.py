"""Integration tests for POST /api/v1/auth/register (USER-01, T-04-02)."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.core.db import get_db  # noqa: E402
from api_service.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.uid = "u_test01"
    user.email = "user@example.com"
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
@patch("api_service.controllers.auth.AuthService.register", new_callable=AsyncMock)
async def test_register_success(mock_register, client):
    """T-04-02 — register success: 201, cookies set, response contains uid (not user_id)."""
    user = _stub_user()
    mock_register.return_value = (user, "access-token-xyz", "refresh-token-xyz")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "Abcdefg1!",
            "confirm_password": "Abcdefg1!",
            "verification_code": "123456",
            "lang": "en",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == 201
    assert body["data"]["uid"] == "u_test01"
    # 用户标识规范: response MUST NOT contain `user_id` (only `uid`)
    assert "user_id" not in body["data"]
    assert "id" not in body["data"]

    # Cookies: both HttpOnly
    cookie_headers = response.headers.get_list("set-cookie")
    cookies_joined = "\n".join(cookie_headers)
    assert "user_access_token=" in cookies_joined
    assert "user_refresh_token=" in cookies_joined
    assert "HttpOnly" in cookies_joined or "httponly" in cookies_joined.lower()
