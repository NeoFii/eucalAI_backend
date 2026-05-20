"""Tests for `services/admin/account_service.py` (admin-on-admin CRUD).

Plan 05-02 / Task 2 behaviours covered:

- `test_create_admin_email_conflict`: duplicate email raises
  AdminConflictException.
- `test_account_service_renamed` (Pitfall 3): the symbol
  `AdminAccountService` exists at `app.service.admin.account_service`
  AND the legacy `AdminManagementService` is NOT present in the module.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from app.common.core.exceptions import AdminConflictException  # noqa: E402


def test_account_service_renamed():
    """Pitfall 3: `AdminAccountService` exists; `AdminManagementService` does NOT."""
    from app.service.admin import account_service as m

    assert hasattr(m, "AdminAccountService")
    assert not hasattr(m, "AdminManagementService"), (
        "Pitfall 3 rename incomplete — `AdminManagementService` must NOT remain "
        "in the module after the Plan 05-02 port."
    )


@pytest.mark.asyncio
async def test_create_admin_email_conflict(mock_super_admin):
    """`AdminAccountService.create_admin` raises AdminConflictException on dup email."""
    from app.service.admin.account_service import AdminAccountService

    db = AsyncMock()

    existing_admin = MagicMock()
    existing_admin.email = "dup@example.com"

    repo = MagicMock()
    repo.get_by_email = AsyncMock(return_value=existing_admin)

    with patch(
        "app.service.admin.account_service.AdminUserRepository",
        return_value=repo,
    ):
        with pytest.raises(AdminConflictException):
            await AdminAccountService.create_admin(
                db,
                actor_admin=mock_super_admin,
                email="dup@example.com",
                name="Dup",
                password="StrongPwd123!",
            )

    # No commit should happen on conflict (the service short-circuits).
    db.commit.assert_not_called()
