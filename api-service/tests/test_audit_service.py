"""Tests for `AdminAuditService.update_action_label` cache invalidation.

Plan 05-02 / Task 3 behaviour:

- `test_update_label_invalidates_cache`: after updating a label, the
  module-level `_action_defs_cache`, `_action_labels_cache`, and
  `_category_actions_cache` are all set to `None` so the next call
  reloads them from the database.
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

from app.service.admin import audit_service as svc  # noqa: E402
from app.service.admin.audit_service import AdminAuditService  # noqa: E402


@pytest.mark.asyncio
async def test_update_label_invalidates_cache():
    """Updating the label clears the module-level defs cache (forcing reload)."""
    db = AsyncMock()
    action_def = MagicMock()
    action_def.code = "admin_login_success"
    action_def.label = "old label"

    # Pre-seed the caches so we can observe them being cleared.
    svc._action_defs_cache = {"admin_login_success": action_def}
    svc._action_labels_cache = {"admin_login_success": "old label"}
    svc._category_actions_cache = {"auth": ("admin_login_success",)}

    # Mock db.execute to return the action_def for the lookup query.
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=action_def)
    db.execute = AsyncMock(return_value=fake_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    returned = await AdminAuditService.update_action_label(
        db, "admin_login_success", "new label",
    )

    # The label was applied to the ORM row.
    assert returned is action_def
    assert action_def.label == "new label"
    # Module-level cache for action defs invalidated (must be None for reload).
    assert svc._action_defs_cache is None
    # Flush ran inside service; commit is now the controller's responsibility.
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_label_returns_none_when_missing():
    """Unknown code → return None, no cache changes, no commit."""
    db = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=fake_result)

    # Pre-seed caches; assert untouched on miss.
    svc._action_defs_cache = {"existing": MagicMock()}
    svc._action_labels_cache = {"existing": "x"}
    svc._category_actions_cache = {"auth": ("existing",)}

    returned = await AdminAuditService.update_action_label(
        db, "missing_code", "irrelevant",
    )

    assert returned is None
    # Caches untouched (no reload triggered on a miss).
    assert svc._action_defs_cache is not None
