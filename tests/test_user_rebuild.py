"""Remaining user-service rebuild coverage."""

from __future__ import annotations

from datetime import datetime, timedelta
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

    starts_at = datetime(2026, 5, 1, 12, 0, 0)
    expires_at = datetime(2026, 6, 1, 12, 0, 0)
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
    assert db.added[0].starts_at == starts_at
    assert db.added[0].expires_at == expires_at
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


def test_user_billing_response_schemas_do_not_expose_internal_ids():
    from user_service.schemas import ApiCallLogItem, BalanceTransactionItem, TopupOrderItem, UsageStatItem

    tx_fields = set(BalanceTransactionItem.model_fields)
    order_fields = set(TopupOrderItem.model_fields)
    stat_fields = set(UsageStatItem.model_fields)
    log_fields = set(ApiCallLogItem.model_fields)

    assert "operator_id" not in tx_fields
    assert "user_id" not in order_fields
    assert "operator_id" not in order_fields
    assert "user_id" not in stat_fields
    assert "user_id" not in log_fields
    assert "ip" not in log_fields
    assert BalanceTransactionItem.__module__ == "user_service.schemas.billing"
    assert TopupOrderItem.__module__ == "user_service.schemas.billing"
    assert UsageStatItem.__module__ == "user_service.schemas.billing"
    assert ApiCallLogItem.__module__ == "user_service.schemas.billing"


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
