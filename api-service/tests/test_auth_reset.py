"""Integration tests for POST /api/v1/auth/reset-password (USER-01, T-04-09)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


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
@patch("app.controller.auth.AuthService.reset_password", new_callable=AsyncMock)
async def test_reset_with_code(mock_reset, client):
    """T-04-09 — reset-password with valid email+code+new_password returns 200."""
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "NewPass1!",
            "lang": "en",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200

    mock_reset.assert_awaited_once()
    args, _ = mock_reset.call_args
    # service called with normalized email + code + new_password + lang
    assert "user@example.com" in args
    assert "123456" in args
    assert "NewPass1!" in args
