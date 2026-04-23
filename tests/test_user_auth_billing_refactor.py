"""Auth and billing refactor coverage for user-service phase 3."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.security import HTTPAuthorizationCredentials

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

USER_ROOT = Path(__file__).resolve().parents[1] / "src" / "user_service"


def _source(path: str) -> str:
    return (USER_ROOT / path).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_get_current_user_only_identifies_pending_user(monkeypatch):
    from user_service.dependencies import get_current_user
    from user_service.models import User

    pending_user = User(
        uid=12345,
        email="pending@example.com",
        password_hash="hash",
        status=2,
    )

    async def fake_get_current_user(_db, uid):
        assert uid == 12345
        return pending_user

    monkeypatch.setattr(
        "user_service.dependencies.decode_token",
        lambda **kwargs: {"type": "access", "uid": 12345},
    )
    monkeypatch.setattr(
        "user_service.dependencies.AuthService.get_current_user",
        fake_get_current_user,
    )

    current_user = await get_current_user(
        request=object(),
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="access-token",
        ),
        access_token=None,
        db=object(),
    )

    assert current_user is pending_user


@pytest.mark.asyncio
async def test_require_active_user_rejects_pending_user(monkeypatch):
    from common.core.exceptions import EmailNotVerifiedException
    from user_service.models import User
    from user_service.policies import require_active_user

    pending_user = User(
        uid=12345,
        email="pending@example.com",
        password_hash="hash",
        status=2,
    )

    with pytest.raises(EmailNotVerifiedException):
        await require_active_user(current_user=pending_user)


def test_gateway_module_exports_admin_invitation_gateway():
    from user_service.gateway import AdminInvitationGateway

    assert AdminInvitationGateway is not None


def test_auth_and_billing_schema_modules_export_current_types():
    from user_service.schemas.auth import RegisterRequest
    from user_service.schemas.billing import (
        ApiCallLogItem,
        BalanceResponseData,
        BalanceTransactionItem,
        TopupOrderItem,
        UsageStatItem,
    )

    assert RegisterRequest is not None
    assert BalanceResponseData is not None
    assert BalanceTransactionItem is not None
    assert TopupOrderItem is not None
    assert UsageStatItem is not None
    assert ApiCallLogItem is not None
    assert RegisterRequest.__module__ == "user_service.schemas.auth"
    assert BalanceResponseData.__module__ == "user_service.schemas.billing"
    assert BalanceTransactionItem.__module__ == "user_service.schemas.billing"
    assert TopupOrderItem.__module__ == "user_service.schemas.billing"
    assert UsageStatItem.__module__ == "user_service.schemas.billing"
    assert ApiCallLogItem.__module__ == "user_service.schemas.billing"


def test_auth_and_billing_services_use_repository_boundaries():
    for path in [
        "services/auth_service.py",
        "services/api_key_service.py",
        "services/balance_service.py",
        "services/email_service.py",
        "services/topup_order_service.py",
        "services/usage_stat_service.py",
    ]:
        source = _source(path)
        assert "user_service.repositories" in source
        assert "from sqlalchemy import" not in source
        assert "select(" not in source
        assert "db.execute(" not in source
        assert "db.add(" not in source


def test_admin_billing_endpoint_removed():
    """admin_billing.py was deprecated and has been deleted."""
    assert not (USER_ROOT / "api" / "v1" / "endpoints" / "admin_billing.py").exists()
