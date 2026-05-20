"""Unit tests for relay/auth.py — API Key three-tier validation (RELAY-05)."""

from __future__ import annotations

import hashlib
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest
import pytest_asyncio

from app.relay.auth import (
    ValidatedApiKey,
    _api_key_cache,
    _principal_from_json,
    _principal_to_json,
    invalidate_api_key_cache,
    require_api_key,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the in-process cache before each test."""
    _api_key_cache.clear()
    yield
    _api_key_cache.clear()


def _make_principal(user_id: int = 1, key_hash: str = "abc123") -> ValidatedApiKey:
    return ValidatedApiKey(
        id=10,
        user_id=user_id,
        key_hash=key_hash,
        status=1,
        quota_mode=0,
        quota_limit=0,
        quota_used=0,
        allowed_models=None,
        allow_ips=None,
        expires_at=None,
        user_rpm_limit=20,
    )


def _make_request(raw_key: str = "sk-test1234567890") -> MagicMock:
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


RAW_KEY = "sk-test1234567890abcdefghijklmnopqrstuvwxyz123456"
KEY_HASH = hashlib.sha256(RAW_KEY.encode()).hexdigest()


@pytest.mark.asyncio
async def test_require_api_key_cache_hit():
    """Tier 1: in-process cache hit — no Redis or DB call."""
    principal = _make_principal(key_hash=KEY_HASH)
    _api_key_cache[KEY_HASH] = principal

    request = _make_request()
    result = await require_api_key(
        request, authorization=f"Bearer {RAW_KEY}", x_api_key=None
    )
    assert result is principal
    assert result.user_id == 1


@pytest.mark.asyncio
async def test_require_api_key_redis_hit():
    """Tier 2: Redis hit — DB not called, cache populated."""
    principal = _make_principal(key_hash=KEY_HASH)
    redis_data = _principal_to_json(principal)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=redis_data)

    request = _make_request()
    with patch("app.relay.auth.get_cache_redis", return_value=mock_redis):
        result = await require_api_key(
            request, authorization=f"Bearer {RAW_KEY}", x_api_key=None
        )

    assert result.id == 10
    assert result.user_id == 1
    # Verify it was written to in-process cache
    assert KEY_HASH in _api_key_cache
    mock_redis.get.assert_called_once_with(f"token:{KEY_HASH}")


@pytest.mark.asyncio
async def test_require_api_key_db_fallback():
    """Tier 3: Redis miss → DB lookup → Redis write-back + cache populated."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    mock_api_key = MagicMock()
    mock_api_key.id = 10
    mock_api_key.user_id = 1
    mock_api_key.key_hash = KEY_HASH
    mock_api_key.status = 1
    mock_api_key.quota_mode = 0
    mock_api_key.quota_limit = 0
    mock_api_key.quota_used = 0
    mock_api_key.allowed_models = None
    mock_api_key.allow_ips = None
    mock_api_key.expires_at = None
    mock_api_key.user_rpm_limit = None

    mock_db = AsyncMock()

    request = _make_request()
    with (
        patch("app.relay.auth.get_cache_redis", return_value=mock_redis),
        patch("app.relay.auth.get_db_context") as mock_ctx,
        patch(
            "app.service.api_key_service.ApiKeyService.validate_by_hash",
            return_value=mock_api_key,
        ),
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await require_api_key(
            request, authorization=f"Bearer {RAW_KEY}", x_api_key=None
        )

    assert result.id == 10
    assert result.user_id == 1
    # Redis write-back called
    mock_redis.set.assert_called_once()
    # In-process cache populated
    assert KEY_HASH in _api_key_cache


@pytest.mark.asyncio
async def test_require_api_key_redis_down_fallback_db():
    """Redis raises exception → falls through to DB successfully."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
    mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))

    mock_api_key = MagicMock()
    mock_api_key.id = 10
    mock_api_key.user_id = 1
    mock_api_key.key_hash = KEY_HASH
    mock_api_key.status = 1
    mock_api_key.quota_mode = 0
    mock_api_key.quota_limit = 0
    mock_api_key.quota_used = 0
    mock_api_key.allowed_models = None
    mock_api_key.allow_ips = None
    mock_api_key.expires_at = None
    mock_api_key.user_rpm_limit = None

    mock_db = AsyncMock()

    request = _make_request()
    with (
        patch("app.relay.auth.get_cache_redis", return_value=mock_redis),
        patch("app.relay.auth.get_db_context") as mock_ctx,
        patch(
            "app.service.api_key_service.ApiKeyService.validate_by_hash",
            return_value=mock_api_key,
        ),
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await require_api_key(
            request, authorization=f"Bearer {RAW_KEY}", x_api_key=None
        )

    assert result.id == 10
    # Still populated in-process cache despite Redis failure
    assert KEY_HASH in _api_key_cache


@pytest.mark.asyncio
async def test_require_api_key_missing_header():
    """No Authorization or X-Api-Key header → 401."""
    from fastapi import HTTPException

    request = _make_request()
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(request, authorization=None, x_api_key=None)
    assert exc_info.value.status_code == 401
    assert "missing api key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_api_key_invalid_key():
    """DB raises ApiKeyNotFoundException → 401."""
    from app.common.core.exceptions import ApiKeyNotFoundException
    from fastapi import HTTPException

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    mock_db = AsyncMock()

    request = _make_request()
    with (
        patch("app.relay.auth.get_cache_redis", return_value=mock_redis),
        patch("app.relay.auth.get_db_context") as mock_ctx,
        patch(
            "app.service.api_key_service.ApiKeyService.validate_by_hash",
            side_effect=ApiKeyNotFoundException(),
        ),
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(
                request, authorization=f"Bearer {RAW_KEY}", x_api_key=None
            )
    assert exc_info.value.status_code == 401


def test_invalidate_api_key_cache():
    """invalidate_api_key_cache removes entry from in-process cache."""
    principal = _make_principal(key_hash="hash_to_remove")
    _api_key_cache["hash_to_remove"] = principal
    assert "hash_to_remove" in _api_key_cache

    invalidate_api_key_cache("hash_to_remove")
    assert "hash_to_remove" not in _api_key_cache
