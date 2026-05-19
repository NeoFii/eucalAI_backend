"""Plan 05-01 Task 2 — super-admin bootstrap tests (ADMIN-12 VALIDATION slots).

Covers:
    test_first_time_create — fresh DB + BOOTSTRAP_SUPERADMIN_ENABLED=True →
        ensure_super_admin() returns True; an admin row + audit row are
        written via the patched repository.
    test_idempotent — count_active_super_admins returns >0 →
        ensure_super_admin() returns False; no lock acquired; no rows
        inserted.
    test_optional — BOOTSTRAP_SUPERADMIN_ENABLED=False with
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=False → returns False
        gracefully. Same config with
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True → raises RuntimeError.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.services.admin.bootstrap_service import AdminBootstrapService

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _stub_db_context(db_mock):
    yield db_mock


# ── T6: first-time create ──────────────────────────────────────────────────────


async def test_first_time_create(mock_db):
    """No super admin exists + bootstrap enabled → create exactly one."""
    repo = MagicMock()
    repo.count_active_super_admins = AsyncMock(return_value=0)
    repo.acquire_named_lock = AsyncMock(return_value=True)
    repo.release_named_lock = AsyncMock(return_value=None)
    # During upsert path the service queries `get_by_email`; return None to
    # exercise the "insert new" branch.
    repo.get_by_email = AsyncMock(return_value=None)

    audit_record = AsyncMock()
    settings_patches = {
        "BOOTSTRAP_SUPERADMIN_ENABLED": True,
        "BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP": True,
        "BOOTSTRAP_SUPERADMIN_EMAIL": "boot@example.com",
        "BOOTSTRAP_SUPERADMIN_PASSWORD": "BootSecret-1!aA",
        "BOOTSTRAP_SUPERADMIN_NAME": "Boot",
        "BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS": False,
        "BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS": False,
    }

    with (
        patch(
            "api_service.services.admin.bootstrap_service.get_db_context",
            return_value=_stub_db_context(mock_db),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.AdminUserRepository",
            return_value=repo,
        ),
        patch(
            "api_service.services.admin.bootstrap_service.AdminAuditService.record",
            new=audit_record,
        ),
        patch(
            "api_service.services.admin.bootstrap_service.hash_password_async",
            new=AsyncMock(return_value="hashed-password"),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.check_password_strength",
            return_value=(True, ""),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.generate_nanoid_uid",
            return_value="adm_BOOT01",
        ),
        patch(
            "api_service.services.admin.bootstrap_service.settings",
            MagicMock(**settings_patches),
        ),
    ):
        created = await AdminBootstrapService.ensure_super_admin()

    assert created is True
    # Lock obtained AND released.
    repo.acquire_named_lock.assert_awaited_once()
    repo.release_named_lock.assert_awaited_once()
    # One admin row added via db.add.
    assert mock_db.add.call_count == 1
    # One audit row written via the patched service.
    audit_record.assert_awaited_once()
    # And the transaction was committed.
    mock_db.commit.assert_awaited()


# ── T7: idempotent ─────────────────────────────────────────────────────────────


async def test_idempotent(mock_db):
    """An active super admin already exists → return False, no lock acquired."""
    repo = MagicMock()
    repo.count_active_super_admins = AsyncMock(return_value=1)
    repo.acquire_named_lock = AsyncMock(return_value=True)
    repo.release_named_lock = AsyncMock(return_value=None)

    settings_patches = {
        "BOOTSTRAP_SUPERADMIN_ENABLED": True,
        "BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP": True,
        "BOOTSTRAP_SUPERADMIN_EMAIL": "boot@example.com",
        "BOOTSTRAP_SUPERADMIN_PASSWORD": "BootSecret-1!aA",
        "BOOTSTRAP_SUPERADMIN_NAME": "Boot",
        "BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS": False,
        "BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS": False,
    }

    with (
        patch(
            "api_service.services.admin.bootstrap_service.get_db_context",
            return_value=_stub_db_context(mock_db),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.AdminUserRepository",
            return_value=repo,
        ),
        patch(
            "api_service.services.admin.bootstrap_service.settings",
            MagicMock(**settings_patches),
        ),
    ):
        created = await AdminBootstrapService.ensure_super_admin()

    assert created is False
    # Idempotent path: lock NOT acquired (no need to enter the create flow).
    repo.acquire_named_lock.assert_not_awaited()
    # No admin row insertion.
    mock_db.add.assert_not_called()


# ── T8: optional bootstrap ─────────────────────────────────────────────────────


async def test_optional(mock_db):
    """BOOTSTRAP_SUPERADMIN_ENABLED=False is allowed iff REQUIRE_ON_STARTUP=False.

    With REQUIRE_ON_STARTUP=True (and no super admin), the same config must
    raise RuntimeError.
    """
    repo = MagicMock()
    repo.count_active_super_admins = AsyncMock(return_value=0)

    permissive_settings = {
        "BOOTSTRAP_SUPERADMIN_ENABLED": False,
        "BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP": False,
        "BOOTSTRAP_SUPERADMIN_EMAIL": None,
        "BOOTSTRAP_SUPERADMIN_PASSWORD": None,
        "BOOTSTRAP_SUPERADMIN_NAME": None,
        "BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS": False,
        "BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS": False,
    }

    with (
        patch(
            "api_service.services.admin.bootstrap_service.get_db_context",
            return_value=_stub_db_context(mock_db),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.AdminUserRepository",
            return_value=repo,
        ),
        patch(
            "api_service.services.admin.bootstrap_service.settings",
            MagicMock(**permissive_settings),
        ),
    ):
        created = await AdminBootstrapService.ensure_super_admin()
    assert created is False

    strict_settings = dict(permissive_settings)
    strict_settings["BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP"] = True

    repo2 = MagicMock()
    repo2.count_active_super_admins = AsyncMock(return_value=0)
    with (
        patch(
            "api_service.services.admin.bootstrap_service.get_db_context",
            return_value=_stub_db_context(mock_db),
        ),
        patch(
            "api_service.services.admin.bootstrap_service.AdminUserRepository",
            return_value=repo2,
        ),
        patch(
            "api_service.services.admin.bootstrap_service.settings",
            MagicMock(**strict_settings),
        ),
    ):
        with pytest.raises(RuntimeError):
            await AdminBootstrapService.ensure_super_admin()
