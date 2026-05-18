"""Unit tests for VoucherService.redeem_code (USER-04, T-04-15).

T-04-15: ref_id idempotency — a duplicate voucher redemption short-circuits via
BillingRepository.exists_by_ref(tx_type=VOUCHER_REDEEM, ref_type='voucher_code',
ref_id=str(code.id)) and does NOT double-credit the user nor insert a second
balance transaction row.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from api_service.models import BalanceTransaction, VoucherRedemptionCode  # noqa: E402
from api_service.services.voucher_service import VoucherService  # noqa: E402


def _stub_code(*, code_id: int = 42, amount: int = 500):
    code = MagicMock()
    code.id = code_id
    code.amount = amount
    code.status = VoucherRedemptionCode.STATUS_ACTIVE
    code.starts_at = datetime(2020, 1, 1, 0, 0, 0)
    code.expires_at = datetime(2099, 1, 1, 0, 0, 0)
    code.created_by_admin_uid = "admin01"
    code.remark = "test voucher"
    return code


def _stub_user(*, balance: int = 0):
    user = MagicMock()
    user.id = 1
    user.balance = balance
    return user


@pytest.mark.asyncio
async def test_redeem_idempotent():
    """T-04-15 — duplicate redeem with idempotent ref_id MUST NOT double-credit
    nor insert a second BalanceTransaction row.

    Sequence:
      1. First call: get_by_hash → fresh ACTIVE code; exists_by_ref → False →
         credit applied, add_tx called once.
      2. Second call: get_by_hash → fresh ACTIVE code again (simulating an attacker
         re-running the request with the same code value, or a concurrent retry
         before the first commit completed). exists_by_ref → True →
         redeem_code short-circuits via ref_id idempotency; add_tx NOT called
         a second time.
    """
    db = AsyncMock()
    user = _stub_user(balance=0)

    # Two fresh code instances — both ACTIVE. In production, the first redeem
    # writes status=REDEEMED but the second concurrent attempt may load a
    # cached/stale row from before that write committed. The ref_id check is
    # the authoritative idempotency boundary.
    code1 = _stub_code(code_id=42, amount=500)
    code2 = _stub_code(code_id=42, amount=500)

    # Patch repository classes used by VoucherService.redeem_code
    with patch(
        "api_service.services.voucher_service.VoucherRepository"
    ) as mock_voucher_cls, patch(
        "api_service.services.voucher_service.UserRepository"
    ) as mock_user_cls, patch(
        "api_service.services.voucher_service.BillingRepository"
    ) as mock_billing_cls:
        mock_voucher_repo = MagicMock()
        mock_voucher_repo.get_by_hash = AsyncMock(side_effect=[code1, code2])
        mock_voucher_cls.return_value = mock_voucher_repo

        mock_user_repo = MagicMock()
        mock_user_repo.get_by_id = AsyncMock(return_value=user)
        mock_user_cls.return_value = mock_user_repo

        mock_billing_repo = MagicMock()
        # First call: not exists → credit applied; second call: exists → skip
        mock_billing_repo.exists_by_ref = AsyncMock(side_effect=[False, True])
        mock_billing_repo.add_tx = MagicMock()
        mock_billing_cls.return_value = mock_billing_repo

        # First redeem — credits the user
        await VoucherService.redeem_code(db, user_id=1, raw_code="testcode1234")
        assert mock_billing_repo.add_tx.call_count == 1, (
            "First redeem must insert exactly one BalanceTransaction"
        )
        # The single add_tx call must reference ref_type='voucher_code', ref_id=str(code.id)
        first_call_args, _ = mock_billing_repo.add_tx.call_args
        tx: BalanceTransaction = first_call_args[0]
        assert tx.ref_type == "voucher_code"
        assert tx.ref_id == str(code1.id)
        assert tx.type == BalanceTransaction.TYPE_VOUCHER_REDEEM

        # Second redeem — exists_by_ref returns True, add_tx must NOT be invoked again
        await VoucherService.redeem_code(db, user_id=1, raw_code="testcode1234")
        assert mock_billing_repo.add_tx.call_count == 1, (
            "Idempotency violated: duplicate redeem must NOT insert a second "
            f"BalanceTransaction (count={mock_billing_repo.add_tx.call_count})"
        )

        # SELECT FOR UPDATE row lock verified — UserRepository.get_by_id called
        # with for_update=True on every redeem attempt.
        for call in mock_user_repo.get_by_id.call_args_list:
            args, kwargs = call
            assert kwargs.get("for_update") is True, (
                "redeem_code must load user row with SELECT FOR UPDATE"
            )


@pytest.mark.asyncio
async def test_normalize_code_is_strip_lower():
    """Pitfall 10 — normalize_code = raw.strip().lower(). Single source of truth."""
    assert VoucherService.normalize_code("  ABC123 ") == "abc123"
    assert VoucherService.normalize_code("hello") == "hello"
    assert VoucherService.normalize_code("\tMixed\n") == "mixed"
