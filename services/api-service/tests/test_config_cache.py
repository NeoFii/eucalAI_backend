"""Unit tests for RoutingConfigCache (RELAY-07, RELAY-08).

Tests cover:
- start() success and failure (D-12)
- load() before/after start
- check_and_reload version poll (D-09)
- Redis failure graceful degradation (D-06)
- Version bump triggers reload (RELAY-08)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest

from api_service.relay.config_cache import RoutingConfigCache


@pytest.fixture
def mock_redis():
    """AsyncMock for Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def mock_session_factory():
    """Mock async session factory that yields a mock session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = session
    return factory


def _make_valid_config() -> dict:
    """Return a minimal valid normalized config dict."""
    return {
        "router_alias": "auto",
        "user_facing_aliases": ["auto"],
        "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
        "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
        "score_bands_raw": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
        "score_bands": [(0.0, 3.0, 5), (3.0, 5.0, 4), (5.0, 7.0, 3), (7.0, 9.0, 2), (9.0, 10.0, 1)],
        "tier_model_map": {1: "gpt-5-4", 2: "minimax-m2-7", 3: "qwen-3-5-397b-a17b", 4: "qwen3-5-flash", 5: "GLM4.7-Flash"},
        "model_providers": {},
        "model_channels": {
            "gpt-5-4": [
                {
                    "channel_slug": "openai:1",
                    "provider_slug": "openai",
                    "api_key": "sk-test",
                    "api_base": "https://api.openai.com/v1",
                    "upstream_model": "gpt-4o",
                    "priority": 0,
                    "weight": 1,
                    "input_price_per_million": 5000000,
                    "output_price_per_million": 15000000,
                    "cached_input_price_per_million": 2500000,
                    "pool_account_id": 1,
                    "rpm_limit": 100,
                    "tpm_limit": None,
                }
            ]
        },
        "model_prices": {"gpt-5-4": {"input": 5000000, "output": 15000000, "cached_input": 2500000}},
        "default_user_rpm": None,
        "system_rpm_cap": None,
    }


def _make_empty_config() -> dict:
    """Return a config with no model_channels and no model_providers."""
    config = _make_valid_config()
    config["model_channels"] = {}
    config["model_providers"] = {}
    return config


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_success(mock_redis, mock_session_factory):
    """start() populates _cached_config when DB returns valid config."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "5"

        await cache.start(mock_session_factory)

    assert cache._cached_config is not None
    assert cache._version == 5
    assert cache._cached_config["model_channels"]["gpt-5-4"] is not None


@pytest.mark.asyncio
async def test_start_empty_config_raises(mock_redis, mock_session_factory):
    """start() raises RuntimeError when model_channels and model_providers are both empty (D-12)."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_empty_config()

        with pytest.raises(RuntimeError, match="no routing config found in DB"):
            await cache.start(mock_session_factory)


@pytest.mark.asyncio
async def test_load_before_start_raises(mock_redis):
    """load() raises RuntimeError if called before start()."""
    cache = RoutingConfigCache(mock_redis)

    with pytest.raises(RuntimeError, match="RoutingConfigCache not started"):
        cache.load()


@pytest.mark.asyncio
async def test_load_returns_cached(mock_redis, mock_session_factory):
    """load() returns the cached config dict after start()."""
    cache = RoutingConfigCache(mock_redis)
    valid_config = _make_valid_config()

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = valid_config
        await cache.start(mock_session_factory)

    result = cache.load()
    assert result == valid_config
    assert result["router_alias"] == "auto"


@pytest.mark.asyncio
async def test_check_and_reload_no_change(mock_redis, mock_session_factory):
    """check_and_reload does NOT reload when version is unchanged."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "3"
        await cache.start(mock_session_factory)

    # Reset mock to track new calls
    mock_redis.get.return_value = "3"  # Same version
    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        await cache.check_and_reload(mock_session_factory)
        mock_load.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_reload_version_bump(mock_redis, mock_session_factory):
    """check_and_reload reloads from DB when version changes (D-09, RELAY-08)."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "1"
        await cache.start(mock_session_factory)

    # Simulate version bump
    new_config = _make_valid_config()
    new_config["router_alias"] = "smart"
    mock_redis.get.return_value = "2"  # Version changed

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = new_config
        await cache.check_and_reload(mock_session_factory)
        mock_load.assert_called_once()

    assert cache._version == 2
    assert cache._cached_config["router_alias"] == "smart"


@pytest.mark.asyncio
async def test_check_and_reload_redis_down(mock_redis, mock_session_factory):
    """check_and_reload gracefully handles Redis failure (D-06 fail-open)."""
    cache = RoutingConfigCache(mock_redis)
    original_config = _make_valid_config()

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = original_config
        mock_redis.get.return_value = "1"
        await cache.start(mock_session_factory)

    # Redis raises exception
    mock_redis.get.side_effect = ConnectionError("Redis connection refused")

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        await cache.check_and_reload(mock_session_factory)
        # Should NOT attempt DB reload when Redis is down
        mock_load.assert_not_called()

    # Config should remain unchanged
    assert cache._cached_config == original_config
    assert cache._version == 1


@pytest.mark.asyncio
async def test_version_bump_triggers_reload(mock_redis, mock_session_factory):
    """Simulate admin INCR: set Redis version to 2, verify new config loaded."""
    cache = RoutingConfigCache(mock_redis)

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = _make_valid_config()
        mock_redis.get.return_value = "1"
        await cache.start(mock_session_factory)

    assert cache._version == 1

    # Admin does INCR routing_config:version -> now 2
    updated_config = _make_valid_config()
    updated_config["model_prices"]["gpt-5-4"]["input"] = 6000000
    mock_redis.get.return_value = "2"

    with patch.object(cache, "_load_from_db", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = updated_config
        await cache.check_and_reload(mock_session_factory)

    assert cache._version == 2
    assert cache._cached_config["model_prices"]["gpt-5-4"]["input"] == 6000000
