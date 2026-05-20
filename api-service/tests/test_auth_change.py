"""Integration tests for POST /api/v1/auth/change-password (USER-01, T-04-08)."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from app.core.db import get_db  # noqa: E402
from app.core.policies import require_active_user  # noqa: E402
from app.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.email = "user@example.com"
    user.status = 1
    user.created_at = datetime(2026, 1, 1, 0, 0, 0)
    return user


@pytest_asyncio.fixture
async def client():
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_active_user] = lambda: _stub_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("app.controller.auth.AuthService.change_password", new_callable=AsyncMock)
async def test_change_revokes_sessions(mock_change, client):
    """T-04-08 — change-password awaits AuthService.change_password (which revokes all sessions).

    Session-revocation itself happens inside AuthService.change_password (via
    _revoke_all_user_sessions) — verified in unit tests. Here we assert the controller
    calls the service correctly and clears cookies on success (forces re-login).
    """
    response = await client.post(
        "/api/v1/auth/change-password",
        json={
            "old_password": "OldPass1!",
            "new_password": "NewPass1!",
            "lang": "en",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200

    mock_change.assert_awaited_once()
    args, _ = mock_change.call_args
    assert "OldPass1!" in args
    assert "NewPass1!" in args

    # Cookies cleared post-change (forces re-login)
    cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(cookie_headers)
    assert "user_access_token=" in joined
    assert "user_refresh_token=" in joined
