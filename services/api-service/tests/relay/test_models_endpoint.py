"""Integration tests for GET /v1/models endpoint (RELAY-04).

Tests model listing with allowed_models filtering (D-19, D-20).
Uses httpx AsyncClient with ASGITransport to test the actual FastAPI app.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest
from httpx import ASGITransport, AsyncClient

from api_service.relay.auth import ValidatedApiKey


def _make_principal(allowed_models: str = "") -> ValidatedApiKey:
    """Create a test ValidatedApiKey principal with configurable allowed_models."""
    return ValidatedApiKey(
        id=1,
        user_id=1,
        key_hash="testhash123",
        status=1,
        quota_mode=0,
        quota_limit=0,
        quota_used=0,
        allowed_models=allowed_models,
        allow_ips=None,
        expires_at=None,
        user_rpm_limit=60,
        balance=10000,
    )


def _mock_config_cache(user_facing_aliases: list[str]) -> MagicMock:
    """Create a mock RoutingConfigCache that returns given aliases."""
    cache = MagicMock()
    cache.load.return_value = {
        "user_facing_aliases": user_facing_aliases,
        "model_channels": {},
        "model_prices": {},
    }
    return cache


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_models_all():
    """GET /v1/models with allowed_models='' returns all user_facing_aliases."""
    principal = _make_principal(allowed_models="")
    config_cache = _mock_config_cache(["gpt-4", "claude-3", "gemini-pro"])

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch(
            "api_service.relay.dependencies.get_routing_config_cache",
            return_value=config_cache,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    assert "gpt-4" in model_ids
    assert "claude-3" in model_ids
    assert "gemini-pro" in model_ids


@pytest.mark.asyncio
async def test_list_models_filtered():
    """GET /v1/models with allowed_models='gpt-4,claude-3' returns only intersection."""
    principal = _make_principal(allowed_models="gpt-4,claude-3")
    config_cache = _mock_config_cache(["gpt-4", "claude-3", "gemini-pro"])

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch(
            "api_service.relay.dependencies.get_routing_config_cache",
            return_value=config_cache,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    model_ids = [m["id"] for m in data["data"]]
    assert "gpt-4" in model_ids
    assert "claude-3" in model_ids
    assert "gemini-pro" not in model_ids


@pytest.mark.asyncio
async def test_list_models_format():
    """Each model object has correct format: id, object='model', created=0, owned_by."""
    principal = _make_principal(allowed_models="")
    config_cache = _mock_config_cache(["gpt-4"])

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch(
            "api_service.relay.dependencies.get_routing_config_cache",
            return_value=config_cache,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    model = data["data"][0]
    assert model["id"] == "gpt-4"
    assert model["object"] == "model"
    assert model["created"] == 0
    assert model["owned_by"] == "eucal-ai"


@pytest.mark.asyncio
async def test_list_models_sorted():
    """Models are returned sorted alphabetically by id."""
    principal = _make_principal(allowed_models="")
    config_cache = _mock_config_cache(["gemini-pro", "claude-3", "gpt-4", "aya-expanse"])

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch(
            "api_service.relay.dependencies.get_routing_config_cache",
            return_value=config_cache,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    model_ids = [m["id"] for m in data["data"]]
    assert model_ids == sorted(model_ids)


@pytest.mark.asyncio
async def test_list_models_no_auth():
    """GET /v1/models without auth returns 401."""
    from api_service.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/models")

    assert resp.status_code == 401
