"""Integration tests for POST /api/v1/auth/refresh (USER-01, T-04-06)."""

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
@patch("api_service.controllers.auth.AuthService.refresh_access_token", new_callable=AsyncMock)
async def test_refresh_rotates(mock_refresh, client):
    """T-04-06 — refresh issues new access + refresh tokens AND sets new cookies."""
    mock_refresh.return_value = ("new-access-token", "new-refresh-token")

    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"user_refresh_token": "old-refresh-token"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["access_token"] == "new-access-token"
    assert body["data"]["refresh_token"] == "new-refresh-token"

    # Both new cookies must be set on the response
    cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(cookie_headers)
    assert "user_access_token=new-access-token" in joined
    assert "user_refresh_token=new-refresh-token" in joined


@pytest.mark.asyncio
async def test_refresh_requires_cookie(client):
    """Without refresh-token cookie, /auth/refresh returns 401."""
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
