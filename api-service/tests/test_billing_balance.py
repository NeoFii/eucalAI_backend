"""Integration tests for GET /api/v1/billing/balance (USER-04, T-04-13).

T-04-13: response includes int fields balance/frozen_amount/used_amount/total_requests/total_tokens
and a computed available_balance = balance - frozen_amount.
"""

from __future__ import annotations

import os
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
@patch("app.controller.billing.BalanceService.get_balance", new_callable=AsyncMock)
async def test_balance_fields(mock_get_balance, client):
    """T-04-13 — /billing/balance returns int fields + computed available_balance."""
    mock_get_balance.return_value = {
        "balance": 1000,
        "frozen_amount": 100,
        "used_amount": 50,
        "total_requests": 10,
        "total_tokens": 500,
    }

    response = await client.get("/api/v1/billing/balance")

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert data["balance"] == 1000
    assert data["frozen_amount"] == 100
    assert data["used_amount"] == 50
    assert data["total_requests"] == 10
    assert data["total_tokens"] == 500
    # Computed field — must equal balance - frozen_amount
    assert data["available_balance"] == 900, (
        f"available_balance must == balance - frozen_amount (=900), got {data['available_balance']}"
    )
