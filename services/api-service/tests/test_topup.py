"""Integration tests for /api/v1/billing/topup-orders (USER-04 topup flow).

The user-facing surface exposes GET /topup-orders only (list user's own orders).
TopupOrderService.create_manual is admin-side (no POST endpoint at this layer).
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

from api_service.common.infra.db.query import PaginatedResult  # noqa: E402
from api_service.core.config import settings  # noqa: E402
from api_service.core.db import get_db  # noqa: E402
from api_service.core.policies import require_active_user  # noqa: E402
from api_service.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    return user


def _stub_order(*, order_no: str = "TP20260101AAAAAAAA", amount: int = 1_000_000, status: int = 1):
    order = MagicMock()
    order.id = 1
    order.order_no = order_no
    order.amount = amount
    order.status = status
    order.payment_channel = "manual"
    order.payment_no = None
    order.paid_at = None
    order.remark = None
    order.updated_at = datetime(2026, 1, 1, 0, 0, 0)
    return order


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
@patch(
    "api_service.controllers.billing.TopupOrderService.get_user_orders",
    new_callable=AsyncMock,
)
async def test_list_topup_orders(mock_get_orders, client):
    """GET /topup-orders returns the user's own paginated top-up orders."""
    mock_get_orders.return_value = PaginatedResult(
        items=[_stub_order(order_no="TP20260101AAAAAAAA", amount=settings.MIN_TOPUP_AMOUNT)],
        total=1,
        page=1,
        page_size=10,
    )

    response = await client.get("/api/v1/billing/topup-orders")

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["order_no"].startswith("TP")


@pytest.mark.asyncio
async def test_topup_order_no_prefix():
    """_generate_order_no produces order numbers prefixed with 'TP' followed by
    YYYYMMDD and 8 random chars (deterministic structure, even if random values
    differ between calls)."""
    from api_service.services.topup_order_service import TopupOrderService

    order_no = TopupOrderService._generate_order_no()
    assert order_no.startswith("TP"), f"order_no must start with TP, got {order_no!r}"
    # TP + 8 digit date + 8 alpha-num suffix
    assert len(order_no) == 2 + 8 + 8, (
        f"order_no length must be 18 (TP + YYYYMMDD + 8 chars), got {len(order_no)}"
    )
