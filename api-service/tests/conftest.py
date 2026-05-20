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


# ──────────────────────────────────────────────────────────────────────────────
# Phase 5 / Plan 05-01 Task 2 — admin-domain fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_admin():
    """Default admin (role=ADMIN, status=ACTIVE) for admin endpoint tests."""
    from app.model.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 1
    admin.uid = "adm_test01"
    admin.email = "admin@example.com"
    admin.name = "Test Admin"
    admin.role = AdminRole.ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = False
    admin.password_hash = "$2b$12$dummyhash"
    admin.login_fail_count = 0
    admin.login_locked_until = None
    admin.password_changed_at = None
    admin.last_login_at = None
    admin.last_login_ip = None
    admin.created_at = datetime(2026, 1, 1, 0, 0, 0)
    admin.updated_at = datetime(2026, 1, 1, 0, 0, 0)
    return admin


@pytest.fixture
def mock_super_admin():
    """Super-admin variant used by privileged endpoint tests."""
    from app.model.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 2
    admin.uid = "adm_super1"
    admin.email = "super@example.com"
    admin.name = "Super Admin"
    admin.role = AdminRole.SUPER_ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = True
    admin.password_hash = "$2b$12$dummyhash"
    admin.login_fail_count = 0
    admin.login_locked_until = None
    admin.password_changed_at = None
    admin.last_login_at = None
    admin.last_login_ip = None
    admin.created_at = datetime(2026, 1, 1, 0, 0, 0)
    admin.updated_at = datetime(2026, 1, 1, 0, 0, 0)
    return admin


@pytest.fixture
def mock_cache_redis():
    """AsyncMock for the Redis db/2 cache layer (used by Plan 05-02/05-03)."""
    m = AsyncMock()
    m.scan_iter = MagicMock()
    m.delete = AsyncMock()
    m.incr = AsyncMock()
    m.get = AsyncMock()
    return m


@pytest.fixture
def mock_internal_client():
    """AsyncMock for the HMAC internal HTTP client (used by Plan 05-03)."""
    m = AsyncMock()
    m.get = AsyncMock()
    m.request = AsyncMock()
    return m
