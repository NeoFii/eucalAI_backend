"""Unit tests for ApiKeyService (USER-04, T-04-12).

T-04-12: ApiKeyService.delete is a SOFT delete — sets deleted_at, never row-deletes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.models import UserApiKey  # noqa: E402
from api_service.services.api_key_service import ApiKeyService  # noqa: E402


@pytest.mark.asyncio
@patch("api_service.services.api_key_service.ApiKeyRepository")
async def test_delete_is_soft(mock_repo_cls):
    """T-04-12 — delete sets deleted_at and commits; no SQL DELETE issued."""
    db = AsyncMock()
    api_key = MagicMock(spec=["deleted_at", "id", "user_id"])
    api_key.deleted_at = None

    mock_repo = MagicMock()
    mock_repo.get_owned_key = AsyncMock(return_value=api_key)
    mock_repo_cls.return_value = mock_repo

    await ApiKeyService.delete(db, key_id=1, user_id=1)

    # Soft delete: deleted_at set to a datetime, NOT None
    assert api_key.deleted_at is not None, "Soft delete: deleted_at must be set"
    assert isinstance(api_key.deleted_at, datetime)
    # Commit awaited — service-layer explicit commit per project convention
    db.commit.assert_awaited()
    # No row-delete: AsyncMock's `db.delete` was never called.
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_status_expired():
    """_refresh_status sets STATUS_EXPIRED when expires_at <= now()."""
    api_key = MagicMock()
    api_key.status = UserApiKey.STATUS_ACTIVE
    api_key.expires_at = datetime(2020, 1, 1, 0, 0, 0)  # in the past
    api_key.is_exhausted = False

    ApiKeyService._refresh_status(api_key)

    assert api_key.status == UserApiKey.STATUS_EXPIRED


@pytest.mark.asyncio
async def test_refresh_status_disabled_short_circuits():
    """_refresh_status leaves STATUS_DISABLED untouched (early return)."""
    api_key = MagicMock()
    api_key.status = UserApiKey.STATUS_DISABLED
    # Even if expired, disabled wins
    api_key.expires_at = datetime(2020, 1, 1, 0, 0, 0)
    api_key.is_exhausted = True

    ApiKeyService._refresh_status(api_key)

    assert api_key.status == UserApiKey.STATUS_DISABLED


@pytest.mark.asyncio
async def test_refresh_status_active_when_unexpired_and_under_quota():
    """_refresh_status promotes to STATUS_ACTIVE for healthy keys."""
    api_key = MagicMock()
    api_key.status = UserApiKey.STATUS_EXPIRED  # stale
    api_key.expires_at = datetime.utcnow() + timedelta(days=30)
    api_key.is_exhausted = False

    ApiKeyService._refresh_status(api_key)

    assert api_key.status == UserApiKey.STATUS_ACTIVE
