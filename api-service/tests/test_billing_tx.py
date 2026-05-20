"""Integration tests for GET /api/v1/billing/transactions (USER-04, T-04-14).

T-04-14: list_transactions paginates and accepts type filter; tx_type passed to service.
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

from app.common.infra.db.query import PaginatedResult  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.policies import require_active_user  # noqa: E402
from app.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    return user


def _stub_tx(*, tx_id: int = 1, tx_type: int = 1, amount: int = 1000):
    tx = MagicMock()
    tx.id = tx_id
    tx.type = tx_type
    tx.amount = amount
    tx.balance_before = 0
    tx.balance_after = amount
    tx.ref_type = "api_call"
    tx.ref_id = f"req-{tx_id}"
    tx.remark = None
    tx.created_at = datetime(2026, 1, 1, 0, 0, 0)
    return tx


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
@patch("app.controller.billing.BalanceService.list_transactions", new_callable=AsyncMock)
async def test_tx_filter_by_type(mock_list_tx, client):
    """T-04-14 — type query parameter is forwarded as tx_type to BalanceService."""
    mock_list_tx.return_value = PaginatedResult(
        items=[_stub_tx(tx_id=1, tx_type=1, amount=100), _stub_tx(tx_id=2, tx_type=1, amount=200)],
        total=2,
        page=1,
        page_size=20,
    )

    response = await client.get("/api/v1/billing/transactions?type=1&page=1&page_size=20")

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 2

    # Crucially: the controller forwarded type=1 as tx_type to the service layer.
    args, kwargs = mock_list_tx.call_args
    assert kwargs.get("tx_type") == 1, (
        f"controller must pass type=1 as tx_type=1 to BalanceService.list_transactions, "
        f"got {kwargs!r}"
    )
