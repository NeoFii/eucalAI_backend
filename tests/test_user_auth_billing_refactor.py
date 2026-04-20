"""Auth and billing refactor coverage for user-service phase 3."""

from __future__ import annotations

import pytest
from fastapi.security import HTTPAuthorizationCredentials


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
    from user_service.schemas.billing import ApiCallLogItem, BalanceResponseData, TopupOrderItem, UsageStatItem
    from user_service.schemas.billing_admin import AdminApiCallLogItem, AdminTopupOrderItem, AdminUsageStatItem

    assert RegisterRequest is not None
    assert BalanceResponseData is not None
    assert TopupOrderItem is not None
    assert UsageStatItem is not None
    assert ApiCallLogItem is not None
    assert AdminTopupOrderItem is not None
    assert AdminUsageStatItem is not None
    assert AdminApiCallLogItem is not None
