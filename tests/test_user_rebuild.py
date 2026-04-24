"""Remaining user-service rebuild coverage."""

from __future__ import annotations

from datetime import datetime, timedelta
import inspect
import os
from types import SimpleNamespace

import pytest

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        if isinstance(self.value, list):
            return len(self.value)
        return self.value

    def scalars(self):
        if isinstance(self.value, list):
            return SimpleNamespace(all=lambda: self.value)
        return SimpleNamespace(all=lambda: [self.value] if self.value is not None else [])


@pytest.mark.asyncio
async def test_balance_service_freeze_writes_ledger():
    from user_service.models import BalanceTransaction, User
    from user_service.services.balance_service import BalanceService

    user = User(id=1, uid=1, email="user@example.com", password_hash="hash", status=1, balance=1000, frozen_amount=0)

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            return ScalarResult(user)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await BalanceService.freeze(db, user_id=1, amount=120, request_id="req-1")

    assert user.balance == 880
    assert user.frozen_amount == 120
    assert db.commit_calls == 1
    assert len(db.added) == 1
    assert isinstance(db.added[0], BalanceTransaction)
    assert db.added[0].type == BalanceTransaction.TYPE_FREEZE
    assert db.added[0].ref_id == "req-1"


@pytest.mark.asyncio
async def test_balance_service_freeze_locks_user_row_before_mutation():
    from user_service.models import User
    from user_service.services.balance_service import BalanceService

    user = User(id=1, uid=1, email="user@example.com", password_hash="hash", status=1, balance=1000, frozen_amount=0)

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult(user)

        def add(self, _obj):
            return None

        async def commit(self):
            return None

    db = FakeSession()
    await BalanceService.freeze(db, user_id=1, amount=120, request_id="req-1")

    assert any(getattr(statement, "_for_update_arg", None) is not None for statement in db.statements)


@pytest.mark.asyncio
async def test_voucher_service_generates_hash_only_redemption_codes(monkeypatch):
    from user_service.models import VoucherRedemptionCode
    from user_service.services.voucher_service import VoucherService

    from datetime import timezone

    starts_at = datetime(2026, 5, 1, 4, 0, 0, tzinfo=timezone.utc)
    expires_at = datetime(2026, 6, 1, 4, 0, 0, tzinfo=timezone.utc)
    generated_codes = iter(["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "f6e5d4c3b2a1f8e7d6c5b4a3f2e1d0c9"])
    monkeypatch.setattr(VoucherService, "_generate_plain_code", staticmethod(lambda: next(generated_codes)))

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit_calls = 0
            self.flush_calls = 0

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

        async def flush(self):
            self.flush_calls += 1

    db = FakeSession()
    generated = await VoucherService.generate_codes(
        db,
        amount=800,
        count=2,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by_admin_uid=99,
        remark="launch credit",
    )

    assert [item.code for item in generated] == ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "f6e5d4c3b2a1f8e7d6c5b4a3f2e1d0c9"]
    assert len(db.added) == 2
    assert all(isinstance(item, VoucherRedemptionCode) for item in db.added)
    assert all(item.code_hash != generated_item.code for item, generated_item in zip(db.added, generated))
    assert db.added[0].code_prefix == "a1b2"
    assert db.added[0].code_suffix == "c5d6"
    assert db.added[0].amount == 800
    assert db.added[0].status == VoucherRedemptionCode.STATUS_ACTIVE
    assert db.added[0].starts_at == datetime(2026, 5, 1, 12, 0, 0)
    assert db.added[0].expires_at == datetime(2026, 6, 1, 12, 0, 0)
    assert db.added[0].created_by_admin_uid == 99
    assert db.added[0].remark == "launch credit"
    assert db.commit_calls == 1
    assert db.flush_calls == 1


@pytest.mark.asyncio
async def test_voucher_service_redeem_credits_user_balance_and_writes_ledger():
    from user_service.models import BalanceTransaction, User, VoucherRedemptionCode
    from user_service.services.voucher_service import VoucherService

    redeem_at = datetime(2026, 5, 1, 12, 0, 0)
    user = User(id=1, uid=1001, email="user@example.com", password_hash="hash", status=1, balance=200)
    code = VoucherRedemptionCode(
        id=10,
        code_hash=VoucherService.hash_code("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"),
        code_prefix="a1b2",
        code_suffix="c5d6",
        amount=800,
        status=VoucherRedemptionCode.STATUS_ACTIVE,
        starts_at=redeem_at - timedelta(hours=1),
        expires_at=redeem_at + timedelta(hours=1),
        created_by_admin_uid=99,
        remark="launch credit",
    )

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0
            self.refresh_calls = 0

        async def execute(self, statement):
            self.execute_calls += 1
            assert getattr(statement, "_for_update_arg", None) is not None
            if self.execute_calls == 1:
                return ScalarResult(code)
            return ScalarResult(user)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

        async def refresh(self, _obj):
            self.refresh_calls += 1

    db = FakeSession()
    redeemed = await VoucherService.redeem_code(
        db,
        user_id=1,
        raw_code=" A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6 ",
        redeemed_at=redeem_at,
    )

    assert redeemed is code
    assert user.balance == 1000
    assert code.status == VoucherRedemptionCode.STATUS_REDEEMED
    assert code.redeemed_user_id == 1
    assert code.redeemed_at == redeem_at
    assert len(db.added) == 1
    assert isinstance(db.added[0], BalanceTransaction)
    assert db.added[0].type == BalanceTransaction.TYPE_VOUCHER_REDEEM
    assert db.added[0].amount == 800
    assert db.added[0].balance_before == 200
    assert db.added[0].balance_after == 1000
    assert db.added[0].ref_type == "voucher_code"
    assert db.added[0].ref_id == "10"
    assert db.commit_calls == 1
    assert db.refresh_calls == 1


@pytest.mark.asyncio
async def test_voucher_service_redeem_rejects_reused_code():
    from common.core.exceptions import ValidationException
    from user_service.models import VoucherRedemptionCode
    from user_service.services.voucher_service import VoucherService

    redeem_at = datetime(2026, 5, 1, 12, 0, 0)
    code = VoucherRedemptionCode(
        id=10,
        code_hash=VoucherService.hash_code("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"),
        code_prefix="a1b2",
        code_suffix="c5d6",
        amount=800,
        status=VoucherRedemptionCode.STATUS_REDEEMED,
        starts_at=redeem_at - timedelta(hours=1),
        expires_at=redeem_at + timedelta(hours=1),
    )

    class FakeSession:
        async def execute(self, statement):
            assert getattr(statement, "_for_update_arg", None) is not None
            return ScalarResult(code)

        def add(self, _obj):
            raise AssertionError("reused codes must not write balance ledger")

        async def commit(self):
            raise AssertionError("reused codes must not commit")

    with pytest.raises(ValidationException, match="代金券兑换码不可用"):
        await VoucherService.redeem_code(
            FakeSession(),
            user_id=1,
            raw_code="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            redeemed_at=redeem_at,
        )


@pytest.mark.asyncio
async def test_balance_service_freeze_uses_balance_only():
    from user_service.models import User
    from user_service.services.balance_service import BalanceService

    user = User(
        id=1,
        uid=1,
        email="user@example.com",
        password_hash="hash",
        status=1,
        balance=1000,
        frozen_amount=0,
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            return ScalarResult(user)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await BalanceService.freeze(db, user_id=1, amount=900, request_id="req-voucher")

    assert user.balance == 100
    assert user.frozen_amount == 900
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_balance_service_freeze_rejects_api_key_quota_overrun():
    from common.core.exceptions import ValidationException
    from user_service.models import User, UserApiKey
    from user_service.services.balance_service import BalanceService

    user = User(
        id=1,
        uid=1,
        email="user@example.com",
        password_hash="hash",
        status=1,
        balance=1000,
        frozen_amount=0,
    )
    api_key = UserApiKey(
        id=10,
        user_id=1,
        key_hash="hash",
        key_prefix="sk-test",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_LIMITED,
        quota_limit=500,
        quota_used=450,
    )

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.commit_calls = 0

        async def execute(self, _statement):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return ScalarResult(user)
            if self.execute_calls == 2:
                return ScalarResult(None)
            return ScalarResult(api_key)

        def add(self, _obj):
            raise AssertionError("no ledger should be written")

        async def commit(self):
            self.commit_calls += 1

    with pytest.raises(ValidationException, match="API Key 限额不足"):
        await BalanceService.freeze(
            FakeSession(),
            user_id=1,
            amount=100,
            request_id="req-limit",
            api_key_id=10,
        )


@pytest.mark.asyncio
async def test_balance_service_topup_rejects_already_paid_order():
    from common.core.exceptions import ValidationException
    from user_service.models import TopupOrder, User
    from user_service.services.balance_service import BalanceService

    user = User(id=1, uid=1, email="user@example.com", password_hash="hash", status=1, balance=1000, frozen_amount=0)
    order = TopupOrder(
        id=10,
        user_id=1,
        order_no="TP20260420ABC",
        amount=500,
        status=TopupOrder.STATUS_PAID,
        payment_channel="manual",
    )

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0

        async def execute(self, statement):
            self.execute_calls += 1
            assert getattr(statement, "_for_update_arg", None) is not None
            if self.execute_calls == 1:
                return ScalarResult(user)
            return ScalarResult(order)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()

    with pytest.raises(ValidationException, match="充值订单状态无效"):
        await BalanceService.topup(
            db,
            user_id=1,
            amount=500,
            order_no=order.order_no,
            operator_id=99,
            remark="manual",
        )

    assert user.balance == 1000
    assert db.added == []
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_topup_order_service_create_manual_writes_order_backed_topup_ledger():
    from user_service.models import BalanceTransaction, TopupOrder, User
    from user_service.services.balance_service import BalanceService

    user = User(id=1, uid=1, email="user@example.com", password_hash="hash", status=1, balance=1000, frozen_amount=0)
    order = TopupOrder(
        id=10,
        user_id=1,
        order_no="TP20260420ABC",
        amount=500,
        status=TopupOrder.STATUS_PENDING,
        payment_channel="manual",
    )

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return ScalarResult(user)
            if self.execute_calls == 2:
                return ScalarResult(order)
            return ScalarResult(None)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await BalanceService.topup(
        db,
        user_id=1,
        amount=500,
        order_no=order.order_no,
        operator_id=99,
        remark="manual topup",
    )

    assert user.balance == 1500
    assert order.status == TopupOrder.STATUS_PAID
    assert db.commit_calls == 1
    assert len(db.added) == 1
    assert db.added[0].type == BalanceTransaction.TYPE_TOPUP
    assert db.added[0].ref_type == "topup_order"
    assert db.added[0].ref_id == order.order_no
    assert db.added[0].operator_id == 99


@pytest.mark.asyncio
async def test_balance_service_admin_adjust_writes_adjust_ledger_without_topup_order():
    from user_service.models import BalanceTransaction, User
    from user_service.services.balance_service import BalanceService

    user = User(id=1, uid=1, email="user@example.com", password_hash="hash", status=1, balance=1000, frozen_amount=0)

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            self.execute_calls += 1
            return ScalarResult(user)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await BalanceService.admin_adjust(
        db,
        user_id=1,
        amount=-300,
        operator_id=99,
        remark="adjust balance",
    )

    assert db.execute_calls == 1
    assert user.balance == 700
    assert db.commit_calls == 1
    assert len(db.added) == 1
    assert db.added[0].type == BalanceTransaction.TYPE_ADMIN_ADJUST
    assert db.added[0].ref_type is None
    assert db.added[0].ref_id is None
    assert db.added[0].operator_id == 99


@pytest.mark.asyncio
async def test_balance_service_settle_consumes_balance_and_counts_quota():
    from user_service.models import User, UserApiKey
    from user_service.services.balance_service import BalanceService

    user = User(
        id=1,
        uid=1,
        email="user@example.com",
        password_hash="hash",
        status=1,
        balance=100,
        frozen_amount=900,
        used_amount=0,
        total_requests=0,
        total_tokens=0,
    )
    api_key = UserApiKey(
        id=10,
        user_id=1,
        key_hash="hash",
        key_prefix="sk-test",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_LIMITED,
        quota_limit=1150,
        quota_used=300,
    )
    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return ScalarResult(user)
            if self.execute_calls == 2:
                return ScalarResult(None)
            return ScalarResult(api_key)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await BalanceService.settle(
        db,
        user_id=1,
        request_id="req-voucher",
        estimated_amount=900,
        actual_amount=850,
        api_key_id=10,
        total_tokens=123,
    )

    assert user.balance == 150
    assert user.frozen_amount == 0
    assert user.used_amount == 850
    assert user.total_requests == 1
    assert user.total_tokens == 123
    assert api_key.quota_used == 1150
    assert api_key.status == UserApiKey.STATUS_EXHAUSTED
    assert db.commit_calls == 1


def test_balance_response_exposes_available_and_frozen_amounts():
    from user_service.schemas import BalanceResponseData

    payload = BalanceResponseData(
        balance=880,
        frozen_amount=120,
        used_amount=300,
        total_requests=2,
        total_tokens=4000,
    )

    assert payload.available_balance == 760
    assert payload.frozen_amount == 120
    assert BalanceResponseData.__module__ == "user_service.schemas.billing"


@pytest.mark.asyncio
async def test_billing_redeem_voucher_endpoint_delegates_to_service(monkeypatch):
    from user_service.api.v1.endpoints.billing import redeem_voucher_code
    from user_service.models import User, VoucherRedemptionCode
    from user_service.schemas.billing import VoucherRedeemRequest

    current_user = User(id=1, uid=1001, email="user@example.com", password_hash="hash", status=1)
    redeemed = VoucherRedemptionCode(
        id=10,
        code_hash="hash",
        code_prefix="a1b2",
        code_suffix="c5d6",
        amount=800,
        status=VoucherRedemptionCode.STATUS_REDEEMED,
        starts_at=datetime(2026, 5, 1, 12, 0, 0),
        expires_at=datetime(2026, 6, 1, 12, 0, 0),
        redeemed_user_id=1,
        redeemed_at=datetime(2026, 5, 2, 12, 0, 0),
    )
    captured = {}

    async def fake_redeem_code(db, *, user_id, raw_code):
        captured["call"] = (db, user_id, raw_code)
        return redeemed

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.VoucherService.redeem_code",
        fake_redeem_code,
    )
    db = object()

    response = await redeem_voucher_code(
        payload=VoucherRedeemRequest(code="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"),
        current_user=current_user,
        db=db,
    )

    assert captured["call"] == (db, 1, "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
    assert response["data"].amount == 800
    assert response["data"].status == VoucherRedemptionCode.STATUS_REDEEMED


@pytest.mark.asyncio
async def test_voucher_service_lists_current_user_redeemed_history(monkeypatch):
    from common.db import ListParams, PaginatedResult
    from user_service.models import VoucherRedemptionCode
    from user_service.services.voucher_service import VoucherService

    redeemed = VoucherRedemptionCode(
        id=10,
        code_hash="secret-hash",
        code_prefix="VC-A",
        code_suffix="0001",
        amount=800,
        status=VoucherRedemptionCode.STATUS_REDEEMED,
        starts_at=datetime(2026, 5, 1, 12, 0, 0),
        expires_at=datetime(2026, 6, 1, 12, 0, 0),
        redeemed_user_id=7,
        redeemed_at=datetime(2026, 5, 2, 12, 0, 0),
    )
    captured = {}

    async def fake_list_for_user_redemptions(self, *, user_id, params):
        captured["call"] = (self.session, user_id, params)
        return PaginatedResult(items=[redeemed], total=1, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.services.voucher_service.VoucherRedemptionCodeRepository.list_for_user_redemptions",
        fake_list_for_user_redemptions,
        raising=False,
    )
    db = object()
    params = ListParams(page=2, page_size=5, order_by="redeemed_at")

    result = await VoucherService.list_user_redemptions(db, user_id=7, params=params)

    assert result.items == [redeemed]
    assert result.total == 1
    assert captured["call"] == (db, 7, params)


@pytest.mark.asyncio
async def test_billing_voucher_redemptions_endpoint_returns_masked_history(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing
    from user_service.models import VoucherRedemptionCode

    redeemed = VoucherRedemptionCode(
        id=10,
        code_hash="secret-hash",
        code_prefix="VC-A",
        code_suffix="0001",
        amount=800,
        status=VoucherRedemptionCode.STATUS_REDEEMED,
        starts_at=datetime(2026, 5, 1, 12, 0, 0),
        expires_at=datetime(2026, 6, 1, 12, 0, 0),
        redeemed_user_id=7,
        redeemed_at=datetime(2026, 5, 2, 12, 0, 0),
        created_at=datetime(2026, 5, 1, 12, 0, 0),
    )
    captured = {}

    async def fake_list_user_redemptions(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[redeemed], total=1, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.VoucherService.list_user_redemptions",
        fake_list_user_redemptions,
        raising=False,
    )

    response = await billing.list_voucher_redemptions(
        page=2,
        page_size=5,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert captured["user_id"] == 7
    assert captured["params"].page == 2
    assert captured["params"].page_size == 5
    assert captured["params"].order_by == "redeemed_at"
    item = response["data"]["items"][0]
    assert item.code_prefix == "VC-A"
    assert item.code_suffix == "0001"
    assert item.amount == 800
    assert item.redeemed_at == datetime(2026, 5, 2, 12, 0, 0)
    assert "code_hash" not in item.model_dump()
    assert "code" not in item.model_dump()


@pytest.mark.asyncio
async def test_billing_voucher_redemptions_endpoint_defaults_page_size_to_10(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing

    captured = {}
    page_size_default = inspect.signature(billing.list_voucher_redemptions).parameters["page_size"].default.default

    async def fake_list_user_redemptions(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[], total=0, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.VoucherService.list_user_redemptions",
        fake_list_user_redemptions,
        raising=False,
    )

    response = await billing.list_voucher_redemptions(
        page=1,
        page_size=page_size_default,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert page_size_default == 10
    assert response["data"]["page"] == 1
    assert response["data"]["page_size"] == 10
    assert captured["user_id"] == 7
    assert captured["params"].page == 1
    assert captured["params"].page_size == 10
    assert captured["params"].order_by == "redeemed_at"


def test_user_billing_response_schemas_do_not_expose_internal_ids():
    from user_service.schemas import (
        ApiCallLogItem,
        BalanceTransactionItem,
        TopupOrderItem,
        UsageStatItem,
        VoucherRedemptionItem,
    )

    tx_fields = set(BalanceTransactionItem.model_fields)
    order_fields = set(TopupOrderItem.model_fields)
    stat_fields = set(UsageStatItem.model_fields)
    log_fields = set(ApiCallLogItem.model_fields)
    voucher_fields = set(VoucherRedemptionItem.model_fields)

    assert "operator_id" not in tx_fields
    assert "user_id" not in order_fields
    assert "operator_id" not in order_fields
    assert "user_id" not in stat_fields
    assert "user_id" not in log_fields
    assert "ip" not in log_fields
    assert "code_hash" not in voucher_fields
    assert "code" not in voucher_fields
    assert {"code_prefix", "code_suffix", "amount", "redeemed_at"} <= voucher_fields
    assert BalanceTransactionItem.__module__ == "user_service.schemas.billing"
    assert TopupOrderItem.__module__ == "user_service.schemas.billing"
    assert UsageStatItem.__module__ == "user_service.schemas.billing"
    assert ApiCallLogItem.__module__ == "user_service.schemas.billing"
    assert VoucherRedemptionItem.__module__ == "user_service.schemas.billing"


def test_api_key_request_normalizes_policy_fields():
    from user_service.schemas import ApiKeyCreateRequest

    payload = ApiKeyCreateRequest(
        name="default",
        allowed_models=" gpt-4o-mini , gpt-4.1 ",
        allow_ips=" 10.0.0.1 \n 2001:db8::/32 ",
    )

    assert payload.allowed_models == "gpt-4o-mini,gpt-4.1"
    assert payload.allow_ips == "10.0.0.1/32\n2001:db8::/32"


def test_api_key_request_rejects_invalid_ip_policy():
    from pydantic import ValidationError
    from user_service.schemas import ApiKeyCreateRequest

    with pytest.raises(ValidationError, match="allow_ips"):
        ApiKeyCreateRequest(name="default", allow_ips="not-an-ip")


@pytest.mark.asyncio
async def test_api_key_service_create_returns_raw_key_and_hashed_model(monkeypatch):
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    monkeypatch.setattr(
        "user_service.services.api_key_service.secrets.choice",
        lambda alphabet: alphabet[0],
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            return ScalarResult([])

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

        async def refresh(self, _obj):
            return None

    db = FakeSession()
    api_key, raw_key = await ApiKeyService.create(db, user_id=10, name="default")

    assert raw_key.startswith("sk-")
    assert len(raw_key) == 49
    assert api_key.key_prefix == raw_key[:8]
    assert api_key.status == UserApiKey.STATUS_ACTIVE
    assert api_key.key_hash != raw_key
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_api_key_service_create_counts_only_non_deleted_keys(monkeypatch):
    from user_service.services.api_key_service import ApiKeyService

    monkeypatch.setattr(
        "user_service.services.api_key_service.secrets.choice",
        lambda alphabet: alphabet[0],
    )

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult([])

        def add(self, _obj):
            return None

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    db = FakeSession()
    await ApiKeyService.create(db, user_id=10, name="default")

    assert "user_api_keys.deleted_at IS NULL" in str(db.statements[0])


@pytest.mark.asyncio
async def test_api_key_service_update_can_clear_optional_policy_fields():
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    api_key = UserApiKey(
        id=101,
        user_id=10,
        key_hash="hash",
        key_prefix="sk-abcd1",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_LIMITED,
        quota_limit=200,
        quota_used=20,
        allowed_models="gpt-4o-mini",
        allow_ips="10.0.0.1/32",
        expires_at=datetime(2026, 4, 30, 12, 0, 0),
    )

    class FakeSession:
        def __init__(self):
            self.commit_calls = 0
            self.refresh_calls = 0

        async def execute(self, _statement):
            return ScalarResult(api_key)

        async def commit(self):
            self.commit_calls += 1

        async def refresh(self, _obj):
            self.refresh_calls += 1

    db = FakeSession()
    updated = await ApiKeyService.update(
        db,
        key_id=101,
        user_id=10,
        allowed_models=None,
        allow_ips=None,
        expires_at=None,
        provided_fields={"allowed_models", "allow_ips", "expires_at"},
    )

    assert updated is api_key
    assert api_key.allowed_models is None
    assert api_key.allow_ips is None
    assert api_key.expires_at is None
    assert db.commit_calls == 1
    assert db.refresh_calls == 1


@pytest.mark.asyncio
async def test_api_key_service_update_missing_key_raises_not_found():
    from common.core.exceptions import ApiKeyNotFoundException
    from user_service.services.api_key_service import ApiKeyService

    class FakeSession:
        async def execute(self, _statement):
            return ScalarResult(None)

    with pytest.raises(ApiKeyNotFoundException) as exc_info:
        await ApiKeyService.update(
            FakeSession(),
            key_id=404,
            user_id=10,
            provided_fields=set(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_api_key_service_delete_marks_deleted_at_without_physical_delete():
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    api_key = UserApiKey(
        id=101,
        user_id=10,
        key_hash="hash",
        key_prefix="sk-abcd1",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_UNLIMITED,
        quota_limit=0,
        quota_used=0,
    )

    class FakeSession:
        def __init__(self):
            self.commit_calls = 0
            self.delete_calls = 0

        async def execute(self, _statement):
            return ScalarResult(api_key)

        async def commit(self):
            self.commit_calls += 1

        async def delete(self, _obj):
            self.delete_calls += 1

    db = FakeSession()
    await ApiKeyService.delete(db, key_id=101, user_id=10)

    assert api_key.deleted_at is not None
    assert db.commit_calls == 1
    assert db.delete_calls == 0


@pytest.mark.asyncio
async def test_api_key_service_list_filters_soft_deleted_keys():
    from user_service.services.api_key_service import ApiKeyService

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult([])

    db = FakeSession()
    listed = await ApiKeyService.list(db, user_id=10)

    assert listed == []
    assert "user_api_keys.deleted_at IS NULL" in str(db.statements[0])


@pytest.mark.asyncio
async def test_api_key_service_validate_by_hash_accepts_matching_model_and_ip():
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    api_key = UserApiKey(
        id=101,
        user_id=10,
        key_hash="hash",
        key_prefix="sk-abcd1",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_UNLIMITED,
        quota_limit=0,
        quota_used=0,
        allowed_models="gpt-4o-mini,gpt-4.1",
        allow_ips="10.0.0.0/24\n2001:db8::/32",
    )

    class FakeSession:
        def __init__(self):
            self.commit_calls = 0
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult(api_key)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    validated = await ApiKeyService.validate_by_hash(
        db,
        "hash",
        model="gpt-4o-mini",
        client_ip="10.0.0.8",
    )

    assert validated is api_key
    assert api_key.last_used_at is not None
    assert db.commit_calls == 1
    assert "user_api_keys.deleted_at IS NULL" in str(db.statements[0])


@pytest.mark.asyncio
async def test_api_key_service_validate_by_hash_rejects_disallowed_model_without_touching_last_used():
    from common.core.exceptions import ApiKeyModelNotAllowedException
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    api_key = UserApiKey(
        id=101,
        user_id=10,
        key_hash="hash",
        key_prefix="sk-abcd1",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_UNLIMITED,
        quota_limit=0,
        quota_used=0,
        allowed_models="gpt-4o-mini,gpt-4.1",
        last_used_at=None,
    )

    class FakeSession:
        def __init__(self):
            self.commit_calls = 0

        async def execute(self, _statement):
            return ScalarResult(api_key)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    with pytest.raises(ApiKeyModelNotAllowedException):
        await ApiKeyService.validate_by_hash(db, "hash", model="gpt-5")

    assert api_key.last_used_at is None
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_api_key_service_validate_by_hash_marks_expired_without_updating_last_used():
    from common.core.exceptions import ApiKeyExpiredException
    from user_service.models import UserApiKey
    from user_service.services.api_key_service import ApiKeyService

    api_key = UserApiKey(
        id=101,
        user_id=10,
        key_hash="hash",
        key_prefix="sk-abcd1",
        name="default",
        status=UserApiKey.STATUS_ACTIVE,
        quota_mode=UserApiKey.MODE_UNLIMITED,
        quota_limit=0,
        quota_used=0,
        expires_at=datetime(2026, 4, 19, 12, 0, 0),
        last_used_at=None,
    )

    class FakeSession:
        def __init__(self):
            self.commit_calls = 0

        async def execute(self, _statement):
            return ScalarResult(api_key)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    with pytest.raises(ApiKeyExpiredException):
        await ApiKeyService.validate_by_hash(db, "hash")

    assert api_key.status == UserApiKey.STATUS_EXPIRED
    assert api_key.last_used_at is None
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_topup_order_service_create_manual_creates_pending_then_paid(monkeypatch):
    from user_service.models import TopupOrder
    from user_service.services.topup_order_service import TopupOrderService

    captured = {}

    async def fake_topup(db, user_id, amount, order_no, operator_id, remark=""):
        captured["call"] = (db, user_id, amount, order_no, operator_id, remark)

    monkeypatch.setattr(
        "user_service.services.topup_order_service.BalanceService.topup",
        fake_topup,
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.flush_calls = 0

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_calls += 1

    db = FakeSession()
    order = await TopupOrderService.create_manual(db, user_id=5, amount=500, operator_id=99, remark="manual")

    assert order.status == TopupOrder.STATUS_PENDING
    assert order.payment_channel == "manual"
    assert order.order_no.startswith("TP")
    assert db.flush_calls == 1
    assert captured["call"][1:] == (5, 500, order.order_no, 99, "manual")


@pytest.mark.asyncio
async def test_usage_stat_service_aggregate_hour_creates_key_and_account_buckets():
    from user_service.models import ApiCallLog, UsageStat
    from user_service.services.usage_stat_service import UsageStatService

    stat_hour = datetime(2026, 4, 20, 10, 0, 0)
    log = ApiCallLog(
        request_id="req-1",
        user_id=7,
        api_key_id=9,
        model_name="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=20,
        cached_tokens=0,
        total_tokens=120,
        cost=15,
        status=ApiCallLog.STATUS_SUCCESS,
        created_at=stat_hour + timedelta(minutes=5),
    )

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0
            self.added = []
            self.commit_calls = 0

        async def execute(self, _statement):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return ScalarResult([log])
            return ScalarResult(None)

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commit_calls += 1

    db = FakeSession()
    await UsageStatService.aggregate_hour(db, stat_hour)

    assert db.commit_calls == 1
    assert len(db.added) == 2
    assert all(isinstance(item, UsageStat) for item in db.added)
    assert {item.api_key_id for item in db.added} == {9, None}


@pytest.mark.asyncio
async def test_billing_usage_logs_default_to_recent_window(monkeypatch):
    from datetime import datetime

    from common.db.query import PaginatedResult
    from user_service.api.v1.endpoints import billing

    fixed_now = datetime(2026, 4, 20, 12, 0, 0)
    captured = {}

    async def fake_list_usage_logs(_db, **kwargs):
        captured.update(kwargs)
        return PaginatedResult(items=[], total=0, page=kwargs["params"].page, page_size=kwargs["params"].page_size)

    monkeypatch.setattr(billing, "now", lambda: fixed_now)
    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.UsageStatService.list_usage_logs",
        fake_list_usage_logs,
    )

    response = await billing.list_usage_logs(
        page=1,
        page_size=20,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response["data"]["total"] == 0
    assert captured["user_id"] == 7
    assert captured["params"].start == fixed_now - timedelta(days=30)
    assert captured["params"].end == fixed_now
    assert captured["params"].time_field == "created_at"


@pytest.mark.asyncio
async def test_billing_usage_logs_forwards_effective_model_filter(monkeypatch):
    from common.db.query import PaginatedResult
    from user_service.api.v1.endpoints import billing

    captured = {}

    async def fake_list_usage_logs(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[], total=0, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.UsageStatService.list_usage_logs",
        fake_list_usage_logs,
    )

    response = await billing.list_usage_logs(
        page=1,
        page_size=20,
        effective_model="gpt-4.1-mini-2026-04-14",
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response["data"]["total"] == 0
    assert captured["user_id"] == 7
    assert captured["effective_model"] == "gpt-4.1-mini-2026-04-14"
    assert captured["params"].order_by == "created_at"


@pytest.mark.asyncio
async def test_usage_stat_service_builds_usage_analytics_from_call_logs(monkeypatch):
    from user_service.models import ApiCallLog
    from user_service.services.usage_stat_service import UsageStatService

    fixed_now = datetime(2026, 4, 24, 16, 45, 0)
    logs = [
        ApiCallLog(
            request_id="req-1",
            user_id=7,
            api_key_id=1,
            model_name="auto",
            selected_model="gpt-4.1-mini-2026-04-14",
            prompt_tokens=100,
            completion_tokens=30,
            cached_tokens=0,
            total_tokens=130,
            cost=100,
            status=ApiCallLog.STATUS_SUCCESS,
            created_at=datetime(2026, 4, 24, 9, 5, 0),
        ),
        ApiCallLog(
            request_id="req-2",
            user_id=7,
            api_key_id=1,
            model_name="claude-3-7-sonnet-2026-02-19",
            selected_model=None,
            prompt_tokens=120,
            completion_tokens=40,
            cached_tokens=0,
            total_tokens=160,
            cost=300,
            status=ApiCallLog.STATUS_ERROR,
            created_at=datetime(2026, 4, 24, 9, 35, 0),
        ),
        ApiCallLog(
            request_id="req-3",
            user_id=7,
            api_key_id=2,
            model_name="auto",
            selected_model="gpt-4.1-mini-2026-04-14",
            prompt_tokens=90,
            completion_tokens=20,
            cached_tokens=0,
            total_tokens=110,
            cost=200,
            status=ApiCallLog.STATUS_SUCCESS,
            created_at=datetime(2026, 4, 24, 15, 10, 0),
        ),
    ]

    class FakeRepo:
        def __init__(self, _db):
            pass

        async def list_analytics_logs(self, *, user_id, start, end):
            assert user_id == 7
            assert start == datetime(2026, 4, 24, 9, 0, 0)
            assert end == datetime(2026, 4, 24, 17, 0, 0)
            return logs

    monkeypatch.setattr("user_service.services.usage_stat_service.now", lambda: fixed_now)
    monkeypatch.setattr("user_service.services.usage_stat_service.UsageStatRepository", FakeRepo)

    analytics = await UsageStatService.get_usage_analytics(
        object(),
        user_id=7,
        range_name="8h",
    )

    assert analytics.range == "8h"
    assert analytics.granularity == "hour"
    assert analytics.start == datetime(2026, 4, 24, 9, 0, 0)
    assert analytics.end == datetime(2026, 4, 24, 17, 0, 0)
    assert analytics.currency == "CNY"
    assert analytics.overview.total_requests == 3
    assert analytics.overview.success_requests == 2
    assert analytics.overview.success_rate == pytest.approx(2 / 3)
    assert analytics.overview.total_cost == 600
    assert analytics.models[0].effective_model == "gpt-4.1-mini-2026-04-14"
    assert analytics.models[0].request_count == 2
    assert analytics.models[0].request_share == pytest.approx(2 / 3)
    assert analytics.models[0].total_cost == 300
    assert analytics.models[1].effective_model == "claude-3-7-sonnet-2026-02-19"
    assert analytics.models[1].request_count == 1
    assert analytics.models[1].request_share == pytest.approx(1 / 3)
    assert analytics.models[1].total_cost == 300
    assert len(analytics.buckets) == 8
    assert analytics.buckets[0].label == "09:00"
    assert analytics.buckets[-1].label == "16:00"
    assert analytics.buckets[1].costs == []
    assert {item.effective_model: item.total_cost for item in analytics.buckets[0].costs} == {
        "gpt-4.1-mini-2026-04-14": 100,
        "claude-3-7-sonnet-2026-02-19": 300,
    }
    assert {item.effective_model: item.total_cost for item in analytics.buckets[6].costs} == {
        "gpt-4.1-mini-2026-04-14": 200,
    }


@pytest.mark.asyncio
async def test_usage_stat_repository_list_usage_logs_filters_by_effective_model_and_orders_latest_first():
    from common.db import ListParams
    from user_service.repositories.usage_stat_repository import UsageStatRepository

    class CountResult:
        def scalar(self):
            return 1

    class ItemsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return CountResult()
            return ItemsResult()

    db = FakeSession()
    repo = UsageStatRepository(db)
    result = await repo.list_usage_logs(
        params=ListParams(page=1, page_size=20, order_by="created_at"),
        user_id=7,
        api_key_id=None,
        model_name=None,
        effective_model="gpt-4.1-mini-2026-04-14",
        request_id=None,
    )

    compiled = db.statements[1].compile(
        compile_kwargs={"literal_binds": True, "render_postcompile": True}
    )
    sql = str(compiled).lower()

    assert result.total == 1
    assert result.items == []
    assert "coalesce(api_call_logs.selected_model, api_call_logs.model_name)" in sql
    assert "= 'gpt-4.1-mini-2026-04-14'" in sql
    assert "order by api_call_logs.created_at desc" in sql


@pytest.mark.asyncio
async def test_balance_tx_repository_list_for_user_uses_paginated_result():
    from common.db.query import ListParams, PaginatedResult
    from user_service.repositories.balance_tx_repository import BalanceTxRepository

    class CountResult:
        def scalar(self):
            return 2

    class ItemsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["tx-1"])

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return CountResult()
            return ItemsResult()

    repo = BalanceTxRepository(FakeSession())
    result = await repo.list_for_user(
        user_id=7,
        params=ListParams(page=2, page_size=5, order_by="created_at"),
    )

    assert isinstance(result, PaginatedResult)
    assert result.items == ["tx-1"]
    assert result.total == 2
    assert result.page == 2
    assert result.page_size == 5


@pytest.mark.asyncio
async def test_balance_tx_repository_list_for_user_filters_type_before_count():
    from common.db.query import ListParams
    from user_service.repositories.balance_tx_repository import BalanceTxRepository

    class CountResult:
        def scalar(self):
            return 1

    class ItemsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["voucher-tx"])

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return CountResult()
            return ItemsResult()

    db = FakeSession()
    repo = BalanceTxRepository(db)
    result = await repo.list_for_user(
        user_id=7,
        params=ListParams(page=1, page_size=20, order_by="created_at"),
        tx_type=7,
    )

    compiled = "\n".join(str(statement) for statement in db.statements)
    assert "balance_transactions.user_id" in compiled
    assert "balance_transactions.type" in compiled
    assert result.total == 1
    assert result.items == ["voucher-tx"]


@pytest.mark.asyncio
async def test_voucher_repository_list_for_user_redemptions_filters_user_and_status():
    from common.db.query import ListParams, PaginatedResult
    from user_service.repositories.voucher_repository import VoucherRedemptionCodeRepository

    class CountResult:
        def scalar(self):
            return 1

    class ItemsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["redeemed-voucher"])

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return CountResult()
            return ItemsResult()

    db = FakeSession()
    repo = VoucherRedemptionCodeRepository(db)
    result = await repo.list_for_user_redemptions(
        user_id=7,
        params=ListParams(page=1, page_size=20, order_by="redeemed_at"),
    )

    compiled = "\n".join(str(statement) for statement in db.statements)
    assert isinstance(result, PaginatedResult)
    assert "voucher_redemption_codes.redeemed_user_id" in compiled
    assert "voucher_redemption_codes.status" in compiled
    assert result.total == 1
    assert result.items == ["redeemed-voucher"]


def test_internal_voucher_item_exposes_redeemed_user_uid_without_internal_fk():
    from user_service.api.v1.endpoints.internal import InternalVoucherItem
    from user_service.models import VoucherRedemptionCode

    voucher = VoucherRedemptionCode(
        id=10,
        code_hash="secret-hash",
        code_prefix="VC-A",
        code_suffix="0001",
        amount=800,
        status=VoucherRedemptionCode.STATUS_REDEEMED,
        starts_at=datetime(2026, 5, 1, 12, 0, 0),
        expires_at=datetime(2026, 6, 1, 12, 0, 0),
        redeemed_user_id=7,
        redeemed_at=datetime(2026, 5, 2, 12, 0, 0),
        created_at=datetime(2026, 5, 1, 12, 0, 0),
        updated_at=datetime(2026, 5, 2, 12, 0, 0),
    )
    voucher.redeemed_user = SimpleNamespace(uid="usr_nan0id123")

    item = InternalVoucherItem.model_validate(voucher)
    payload = item.model_dump()

    assert item.redeemed_user_uid == "usr_nan0id123"
    assert "redeemed_user_id" not in payload


@pytest.mark.asyncio
async def test_user_repository_searches_trimmed_uid_or_email_with_escaped_like():
    from user_service.repositories.user_repository import UserRepository

    class CountResult:
        def scalar(self):
            return 0

    class ItemsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return CountResult()
            return ItemsResult()

    db = FakeSession()
    await UserRepository(db).list_users(search=" usr_100% ")

    compiled = "\n".join(str(statement) for statement in db.statements)
    params = {}
    for statement in db.statements:
        params.update(statement.compile().params)

    assert "users.uid =" in compiled
    assert "users.uid LIKE" in compiled
    assert "users.email LIKE" in compiled
    assert any(value == "usr_100%" for value in params.values())
    assert any(value == "usr\\_100\\%%" for value in params.values())


@pytest.mark.asyncio
async def test_balance_service_list_transactions_passes_type_filter(monkeypatch):
    from common.db import ListParams, PaginatedResult
    from user_service.services.balance_service import BalanceService

    captured = {}

    async def fake_list_for_user(self, *, user_id, params, tx_type=None):
        captured["call"] = (self.session, user_id, params, tx_type)
        return PaginatedResult(items=["voucher-tx"], total=1, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.services.balance_service.BalanceTxRepository.list_for_user",
        fake_list_for_user,
    )
    db = object()
    params = ListParams(page=1, page_size=20, order_by="created_at")

    result = await BalanceService.list_transactions(db, user_id=7, params=params, tx_type=7)

    assert result.items == ["voucher-tx"]
    assert captured["call"] == (db, 7, params, 7)


@pytest.mark.asyncio
async def test_billing_transactions_endpoint_defaults_page_size_to_10(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing

    captured = {}
    page_size_default = inspect.signature(billing.list_transactions).parameters["page_size"].default.default

    async def fake_list_transactions(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[], total=0, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.BalanceService.list_transactions",
        fake_list_transactions,
    )

    response = await billing.list_transactions(
        page=1,
        page_size=page_size_default,
        type=None,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert page_size_default == 10
    assert response["data"]["page"] == 1
    assert response["data"]["page_size"] == 10
    assert captured["user_id"] == 7
    assert captured["tx_type"] is None
    assert captured["params"].page == 1
    assert captured["params"].page_size == 10


@pytest.mark.asyncio
async def test_billing_transactions_endpoint_passes_type_filter(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing

    captured = {}

    async def fake_list_transactions(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[], total=0, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.BalanceService.list_transactions",
        fake_list_transactions,
    )

    response = await billing.list_transactions(
        page=3,
        page_size=25,
        type=7,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response["data"]["total"] == 0
    assert captured["user_id"] == 7
    assert captured["tx_type"] == 7
    assert captured["params"].page == 3
    assert captured["params"].page_size == 25


@pytest.mark.asyncio
async def test_billing_topup_orders_endpoint_defaults_page_size_to_10(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing
    from user_service.models import TopupOrder

    order = TopupOrder(
        id=10,
        user_id=7,
        order_no="TP202604230001",
        amount=500,
        status=TopupOrder.STATUS_PAID,
        payment_channel="manual",
        paid_at=datetime(2026, 4, 23, 10, 0, 0),
        created_at=datetime(2026, 4, 23, 9, 50, 0),
        updated_at=datetime(2026, 4, 23, 10, 0, 0),
    )
    captured = {}
    page_size_default = inspect.signature(billing.list_topup_orders).parameters["page_size"].default.default

    async def fake_get_user_orders(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[order], total=1, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.TopupOrderService.get_user_orders",
        fake_get_user_orders,
    )

    response = await billing.list_topup_orders(
        page=1,
        page_size=page_size_default,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert page_size_default == 10
    assert response["data"]["page"] == 1
    assert response["data"]["page_size"] == 10
    assert captured["user_id"] == 7
    assert captured["params"].page == 1
    assert captured["params"].page_size == 10
    assert captured["params"].order_by == "created_at"
    assert response["data"]["items"][0].order_no == "TP202604230001"


@pytest.mark.asyncio
async def test_billing_topup_orders_endpoint_passes_explicit_page_size(monkeypatch):
    from common.db import PaginatedResult
    from user_service.api.v1.endpoints import billing

    captured = {}

    async def fake_get_user_orders(_db, **kwargs):
        captured.update(kwargs)
        params = kwargs["params"]
        return PaginatedResult(items=[], total=0, page=params.page, page_size=params.page_size)

    monkeypatch.setattr(
        "user_service.api.v1.endpoints.billing.TopupOrderService.get_user_orders",
        fake_get_user_orders,
    )

    response = await billing.list_topup_orders(
        page=2,
        page_size=25,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert response["data"]["page"] == 2
    assert response["data"]["page_size"] == 25
    assert captured["user_id"] == 7
    assert captured["params"].page == 2
    assert captured["params"].page_size == 25


@pytest.mark.asyncio
async def test_billing_usage_rejects_time_ranges_over_90_days():
    from common.core.exceptions import ValidationException
    from user_service.api.v1.endpoints import billing

    with pytest.raises(ValidationException, match="时间范围不能超过 90 天"):
        await billing.list_usage_stats(
            start=datetime(2026, 1, 1),
            end=datetime(2026, 4, 20),
            current_user=SimpleNamespace(id=7),
            db=object(),
        )


def test_user_worker_settings_expose_jobs_and_crons():
    from user_service.worker import WorkerSettings

    assert hasattr(WorkerSettings, "functions")
    assert hasattr(WorkerSettings, "cron_jobs")
    assert hasattr(WorkerSettings, "redis_settings")
    assert {fn.__name__ for fn in WorkerSettings.functions} == {
        "aggregate_usage_stats",
        "cleanup_expired_verification_codes",
    }
