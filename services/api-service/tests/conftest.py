"""Shared pytest fixtures for api-service tests (Phase 4 Wave 0)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_user():
    """A MagicMock user with stable values for /auth, /keys, /billing tests."""
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    user.email = "test@example.com"
    user.email_verified_at = datetime(2026, 1, 1, 0, 0, 0)
    user.last_login_at = None
    user.created_at = datetime(2026, 1, 1, 0, 0, 0)
    user.rpm_limit = 20
    user.password_hash = "$2b$12$dummyhash"
    user.is_login_locked = False
    user.login_fail_count = 0
    user.login_locked_until = None
    return user


@pytest.fixture
def mock_db():
    """AsyncMock standing in for AsyncSession. Repository methods are patched per test."""
    return AsyncMock()


@pytest.fixture
def arq_pool_mock():
    """AsyncMock exposing enqueue_job for asserting D-02 ARQ behaviour."""
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return pool


@pytest.fixture
def redis_mock():
    """AsyncMock for the cache redis layer."""
    return AsyncMock()
