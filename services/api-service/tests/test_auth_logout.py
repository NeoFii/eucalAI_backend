"""Integration tests for POST /api/v1/auth/logout (USER-01, T-04-05)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.core.db import get_db  # noqa: E402
from api_service.main import app  # noqa: E402


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
@patch("api_service.controllers.auth.AuthService.logout", new_callable=AsyncMock)
async def test_logout_revokes_session(mock_logout, client):
    """T-04-05 — logout: AuthService.logout called with refresh cookie, both cookies cleared."""
    response = await client.post(
        "/api/v1/auth/logout",
        cookies={"user_refresh_token": "the-refresh-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200

    # Service called with the refresh token from cookie
    mock_logout.assert_awaited_once()
    args, _ = mock_logout.call_args
    assert "the-refresh-token" in args  # passed as second positional arg

    # Both cookies cleared (Max-Age=0 or expires in the past)
    cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(cookie_headers)
    assert "user_access_token=" in joined
    assert "user_refresh_token=" in joined
    # delete_cookie issues Max-Age=0 or an expired Expires header
    assert ("Max-Age=0" in joined) or ("max-age=0" in joined) or ("expires=" in joined.lower())
