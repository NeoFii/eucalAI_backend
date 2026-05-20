"""Integration tests for GET /api/v1/billing/usage (USER-04, T-04-16).

T-04-16: ListParams.validate_time_range enforces max_span_days=MAX_BILLING_RANGE_DAYS (90).
A range > 90 days raises ValidationException → 422 response.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

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
    user.status = 1
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
async def test_range_capped(client):
    """T-04-16 — /billing/usage with start..end spanning >90 days is rejected.

    ValidationException is raised inside _build_list_params and converted to a
    422 response by the global exception handler.
    """
    # start=2024-01-01, end=2024-06-01 → 152 days > 90-day cap
    response = await client.get(
        "/api/v1/billing/usage"
        "?start=2024-01-01T00:00:00&end=2024-06-01T00:00:00"
    )

    # ValidationException (HTTP 422) — see common/core/exceptions.py:38-47
    assert response.status_code == 422, response.text
    body = response.json()
    # Detail surfaces the 90-day cap message from ListParams.validate_time_range
    detail = body.get("detail") or body.get("message", "")
    assert "90" in str(detail) or "时间" in str(detail), (
        f"expected 90-day cap error message, got {body!r}"
    )
