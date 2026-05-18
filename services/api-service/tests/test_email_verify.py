"""Tests for EmailService.get_valid_code_or_raise (USER-06, T-04-23, D-11).

Covers:
- T-04-23 test_error_count: on wrong code, error_count is incremented and db.commit() is awaited
  (D-11 inner commit preserved).
- test_lockout_at_max_errors: after MAX_CODE_ERRORS, sets locked_until and commits before raising.
"""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.common.core.exceptions import InvalidCodeException  # noqa: E402
from api_service.common.utils.timezone import now  # noqa: E402
from api_service.core.config import settings  # noqa: E402
from api_service.services.email_service import EmailService  # noqa: E402


def _make_code_record(error_count: int = 0) -> MagicMock:
    record = MagicMock()
    record.error_count = error_count
    record.locked_until = None
    record.expires_at = now() + timedelta(minutes=5)
    record.code_hash = "$2b$12$mockhash"
    return record


@pytest.mark.asyncio
@patch("api_service.services.email_service.verify_password_async", new_callable=AsyncMock)
@patch("api_service.services.email_service.UserRepository")
async def test_error_count(mock_repo_cls, mock_verify):
    """T-04-23 — wrong code raises InvalidCodeException, increments error_count, and commits (D-11)."""
    db = AsyncMock()
    record = _make_code_record(error_count=0)

    mock_repo = MagicMock()
    mock_repo.email_code_latest_unused_for_email = AsyncMock(return_value=record)
    mock_repo_cls.return_value = mock_repo

    mock_verify.return_value = False  # wrong code

    with pytest.raises(InvalidCodeException):
        await EmailService.get_valid_code_or_raise(db, "user@example.com", "000000", "register")

    assert record.error_count == 1, f"error_count should increment 0→1, got {record.error_count}"
    db.commit.assert_awaited()  # D-11: inner commit MUST run


@pytest.mark.asyncio
@patch("api_service.services.email_service.verify_password_async", new_callable=AsyncMock)
@patch("api_service.services.email_service.UserRepository")
async def test_lockout_at_max_errors(mock_repo_cls, mock_verify):
    """After MAX_CODE_ERRORS, locked_until is set, db.commit awaited, InvalidCodeException raised."""
    db = AsyncMock()
    record = _make_code_record(error_count=settings.MAX_CODE_ERRORS - 1)

    mock_repo = MagicMock()
    mock_repo.email_code_latest_unused_for_email = AsyncMock(return_value=record)
    mock_repo_cls.return_value = mock_repo

    mock_verify.return_value = False  # wrong code → error_count becomes MAX_CODE_ERRORS

    with pytest.raises(InvalidCodeException, match="(?i)too many"):
        await EmailService.get_valid_code_or_raise(db, "user@example.com", "000000", "register")

    assert record.error_count == settings.MAX_CODE_ERRORS
    assert record.locked_until is not None, "locked_until must be set when threshold reached"
    db.commit.assert_awaited()  # D-11: inner commit MUST run
