"""Tests for EmailService.send_verification_code (USER-06, T-04-21, T-04-22).

Covers:
- T-04-21 test_daily_limit: rate-limit at CODE_DAILY_SEND_LIMIT (3/day per email+purpose).
- T-04-22 test_enqueues_arq: D-02 behavior — pool.enqueue_job called with literal
  "send_verification_email" (Pitfall 9 verified).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

# Settings must be configured before importing api_service.* (BaseServiceSettings
# validates required fields at import time).
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.services.email_service import EmailService  # noqa: E402


@pytest.mark.asyncio
@patch("api_service.services.email_service.get_arq_pool")
@patch("api_service.services.email_service.UserRepository")
async def test_daily_limit(mock_repo_cls, mock_pool_fn):
    """T-04-21 — when count >= CODE_DAILY_SEND_LIMIT, returns (False, ...) and does NOT enqueue."""
    from api_service.core.config import settings

    db = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.email_code_count_created_since = AsyncMock(
        return_value=settings.CODE_DAILY_SEND_LIMIT,
    )
    mock_repo_cls.return_value = mock_repo

    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    mock_pool_fn.return_value = pool

    sent, message = await EmailService.send_verification_code(db, "user@example.com", "register")

    assert sent is False
    assert "limit" in message.lower() or "limit reached" in message.lower()
    # Crucially: enqueue must NOT happen when rate-limited.
    pool.enqueue_job.assert_not_called()


@pytest.mark.asyncio
@patch("api_service.services.email_service.hash_password_async", new_callable=AsyncMock)
@patch("api_service.services.email_service.get_arq_pool")
@patch("api_service.services.email_service.UserRepository")
async def test_enqueues_arq(mock_repo_cls, mock_pool_fn, mock_hash):
    """T-04-22 (D-02) — on a successful send_verification_code, pool.enqueue_job is called
    with the literal job name "send_verification_email" (Pitfall 9 verified) and 3 positional args."""
    db = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.email_code_count_created_since = AsyncMock(return_value=0)
    mock_repo.email_code_latest_for_email = AsyncMock(return_value=None)
    mock_repo.email_code_list_unused_for_email = AsyncMock(return_value=[])
    mock_repo.email_code_add = MagicMock(return_value=None)
    mock_repo_cls.return_value = mock_repo

    mock_hash.return_value = "$2b$12$mockhash"

    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    mock_pool_fn.return_value = pool

    sent, message = await EmailService.send_verification_code(db, "user@example.com", "register")

    assert sent is True, message
    # Crucially: enqueue MUST happen on the request path; SMTP is deferred to the worker (D-02).
    pool.enqueue_job.assert_called_once()
    args, kwargs = pool.enqueue_job.call_args
    assert args[0] == "send_verification_email", (
        f"Pitfall 9: enqueue job name must literally equal "
        f'"send_verification_email", got {args[0]!r}'
    )
    # email + code + purpose positional args
    assert args[1] == "user@example.com"
    assert isinstance(args[2], str) and len(args[2]) == 6 and args[2].isdigit()
    assert args[3] == "register"


@pytest.mark.asyncio
@patch("api_service.services.email_service.get_arq_pool")
@patch("api_service.services.email_service.UserRepository")
async def test_lockout_prevents_send(mock_repo_cls, mock_pool_fn):
    """When latest code is locked_until > now(), returns (False, ...) and does NOT enqueue."""
    from datetime import timedelta

    from api_service.common.utils.timezone import now

    db = AsyncMock()
    locked = MagicMock()
    locked.locked_until = now() + timedelta(hours=1)

    mock_repo = MagicMock()
    mock_repo.email_code_count_created_since = AsyncMock(return_value=0)
    mock_repo.email_code_latest_for_email = AsyncMock(return_value=locked)
    mock_repo_cls.return_value = mock_repo

    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    mock_pool_fn.return_value = pool

    sent, message = await EmailService.send_verification_code(db, "user@example.com", "register")

    assert sent is False
    assert "locked" in message.lower()
    pool.enqueue_job.assert_not_called()
