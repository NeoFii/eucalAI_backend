"""Integration tests for /api/v1/keys endpoints (USER-04, T-04-10 + T-04-11).

Critical security invariants:
- T-04-10: POST /keys returns plaintext key EXACTLY ONCE in data.key on create;
  data.item never contains `key` or `key_hash`.
- T-04-11: GET /keys returns items with key_prefix only; no item exposes `key`
  or `key_hash`.
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

from app.core.db import get_db  # noqa: E402
from app.core.policies import require_active_user  # noqa: E402
from app.main import app  # noqa: E402


def _stub_user():
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    return user


def _stub_api_key(*, prefix: str = "sk-AAAA", name: str = "test", key_id: int = 1):
    obj = MagicMock()
    obj.id = key_id
    obj.key_prefix = prefix
    obj.name = name
    obj.status = 1
    obj.quota_mode = 1
    obj.quota_limit = 0
    obj.quota_used = 0
    obj.allowed_models = None
    obj.allow_ips = None
    obj.expires_at = None
    obj.last_used_at = None
    obj.created_at = datetime(2026, 1, 1, 0, 0, 0)
    obj.updated_at = datetime(2026, 1, 1, 0, 0, 0)
    return obj


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
@patch("app.controller.keys.ApiKeyService.create", new_callable=AsyncMock)
async def test_create_returns_plaintext_once(mock_create, client):
    """T-04-10 — POST /keys returns plaintext key exactly once on create; the
    ApiKeyItem inside `data.item` exposes `key_prefix` but NEVER `key` or `key_hash`."""
    raw_plaintext = "sk-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLLMM"
    stub = _stub_api_key(prefix="sk-AAAA", name="test")
    mock_create.return_value = (stub, raw_plaintext)

    response = await client.post("/api/v1/keys", json={"name": "test"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == 201
    data = body["data"]
    # Plaintext appears exactly once, in data.key
    assert data["key"] == raw_plaintext
    # The item view exposes key_prefix but neither plaintext nor hash
    assert data["item"]["key_prefix"] == "sk-AAAA"
    assert "key" not in data["item"], (
        "Security invariant violated: ApiKeyItem exposed plaintext `key`"
    )
    assert "key_hash" not in data["item"], (
        "Security invariant violated: ApiKeyItem exposed `key_hash`"
    )


@pytest.mark.asyncio
@patch("app.controller.keys.ApiKeyService.list", new_callable=AsyncMock)
async def test_list_no_secrets(mock_list, client):
    """T-04-11 — GET /keys never exposes plaintext key or key_hash."""
    mock_list.return_value = [
        _stub_api_key(prefix="sk-AAAA", name="first", key_id=1),
        _stub_api_key(prefix="sk-BBBB", name="second", key_id=2),
    ]

    response = await client.get("/api/v1/keys")

    assert response.status_code == 200, response.text
    body = response.json()
    items = body["data"]
    assert len(items) == 2
    for item in items:
        assert "key_prefix" in item
        assert "key" not in item, (
            f"Security invariant violated: list exposed plaintext `key` in {item!r}"
        )
        assert "key_hash" not in item, (
            f"Security invariant violated: list exposed `key_hash` in {item!r}"
        )
