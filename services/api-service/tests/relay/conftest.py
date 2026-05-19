"""Shared fixtures for relay tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.relay.auth import ValidatedApiKey
from api_service.relay.sdk_clients import SdkClientPool


def make_test_principal(**overrides) -> ValidatedApiKey:
    """Create a test ValidatedApiKey principal with sensible defaults."""
    defaults = dict(
        id=1,
        user_id=1,
        key_hash="testhash123",
        status=1,
        quota_mode=0,
        quota_limit=0,
        quota_used=0,
        allowed_models="",
        allow_ips=None,
        expires_at=None,
        user_rpm_limit=60,
        balance=10000,
    )
    defaults.update(overrides)
    return ValidatedApiKey(**defaults)


@pytest.fixture
def mock_redis():
    """AsyncMock standing in for redis.asyncio.Redis."""
    m = AsyncMock()
    m.register_script = MagicMock(return_value=AsyncMock(return_value=1))
    return m


@pytest.fixture
def mock_sdk_client_pool():
    """A real SdkClientPool instance with small max_size for testing."""
    return SdkClientPool(max_size=3)


@pytest.fixture
def mock_settings():
    """MagicMock settings with RATE_LIMIT_* configuration."""
    s = MagicMock()
    s.RATE_LIMIT_ENABLED = True
    s.RATE_LIMIT_DEFAULT_USER_RPM = 20
    s.RATE_LIMIT_GLOBAL_RPM = 100
    s.SDK_CLIENT_POOL_MAX_SIZE = 64
    s.ANTHROPIC_NATIVE_SLUGS = ["anthropic"]
    return s
