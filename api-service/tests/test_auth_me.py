"""Integration tests for GET /api/v1/auth/me (USER-01, T-04-07).

Critical assertion: response data MUST contain `uid` but NOT `user_id` (root CLAUDE.md
用户标识规范). Also asserts default_rpm = settings.DEFAULT_USER_RPM (D-09).
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from app.core.config import settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.policies import require_active_user  # noqa: E402
from app.main import app  # noqa: E402


def _stub_user(rpm_limit=None):
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.email = "user@example.com"
    user.status = 1
    user.email_verified_at = datetime(2026, 1, 1, 0, 0, 0)
    user.last_login_at = None
    user.created_at = datetime(2026, 1, 1, 0, 0, 0)
    user.rpm_limit = rpm_limit
    return user


@pytest_asyncio.fixture
async def client():
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_active_user] = lambda: _stub_user(rpm_limit=42)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("app.controller.auth.BillingRepository")
async def test_me_excludes_id(mock_billing_cls, client):
    """T-04-07 — /auth/me returns uid + default_rpm (D-09 settings constant) + current_tpm.
    Response data must NOT include `user_id` (root CLAUDE.md 用户标识规范)."""
    billing_repo = MagicMock()
    billing_repo.stat_get_user_tpm_last_minute = AsyncMock(return_value=42)
    mock_billing_cls.return_value = billing_repo

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    # 用户标识规范: ONLY uid; never user_id
    assert "uid" in data and data["uid"] == "u_test01"
    assert "user_id" not in data
    # D-09: default_rpm comes from settings constant
    assert data["default_rpm"] == settings.DEFAULT_USER_RPM
    # current_tpm from BillingRepository (Phase 3 D-04 merge)
    assert data["current_tpm"] == 42
    # rpm_limit may be NULL or per-user override
    assert data["rpm_limit"] == 42
