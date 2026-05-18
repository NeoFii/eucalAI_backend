"""Shared pytest fixtures for api-service tests (Phase 4 Wave 0).

Plan 05-01 (Task 2) extends this with admin-domain fixtures
(`mock_admin`, `mock_super_admin`, `mock_cache_redis`, `mock_internal_client`).
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# Provide reasonable test defaults BEFORE any pydantic-settings model loads.
# Individual test modules historically set these per-file; centralising here
# also lets new test files (Plan 05-01 / test_schemas_hoist.py) import
# settings without per-file env boilerplate.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest  # noqa: E402


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
