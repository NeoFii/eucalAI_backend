from __future__ import annotations

import json
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.skip(
    "Covers legacy router_service (keys/billing/openai-compat) replaced by the "
    "ML router; re-enable once key/billing features are reintroduced.",
    allow_module_level=True,
)

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"


class _ScalarResult:
    def __init__(self, *, scalar_one_or_none=None):
        self._scalar_one_or_none = scalar_one_or_none

    def scalar_one_or_none(self):
        return self._scalar_one_or_none


@pytest.mark.asyncio
async def test_invitation_code_generation_to_user_registration_flow(monkeypatch):
    from admin_service.api.v1.endpoints.invitation import (
        GenerateInvitationCodeRequest,
        generate_invitation_codes,
    )
    from user_service.schemas import RegisterRequest
    from user_service.services.auth_service import AuthService

    created_at = datetime.now()
    invitation_state: dict[str, dict[str, object]] = {}

    async def fake_generate(*, db, created_by, quantity, expires_days, expires_at, max_uses, remark):
        del db, quantity, expires_days, expires_at, max_uses, remark
        code = "INVITE-E2E-001"
        invitation_state[code] = {"created_by": created_by, "consumed": False, "used_by": None}
        return [
            SimpleNamespace(
                id=1,
                code=code,
                status=0,
                expires_at=None,
                used_by=None,
                used_at=None,
                remark=None,
                created_at=created_at,
            )
        ]

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.InvitationCodeService.generate",
        fake_generate,
    )

    generation = await generate_invitation_codes(
        request=GenerateInvitationCodeRequest(quantity=1, expires_days=7, max_uses=1),
        current_admin=SimpleNamespace(id=9001, uid=9001),
        db=object(),
    )
    code = generation.data.codes[0].code

    async def fake_verify_code(_db, email, code_value, purpose):
        assert email == "user@example.com"
        assert code_value == "123456"
        assert purpose == "register"

    async def fake_consume_invitation(code_value, used_by_uid):
        invitation_state[code_value]["consumed"] = True
        invitation_state[code_value]["used_by"] = used_by_uid

    monkeypatch.setattr(
        "user_service.services.auth_service.email_service.verify_code_or_raise",
        fake_verify_code,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AuthService._admin_gateway.consume_invitation_code",
        fake_consume_invitation,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.generate_snowflake_id",
        lambda: 424242,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.hash_password",
        lambda password: f"hash:{password}",
    )

    class FakeSession:
        def __init__(self):
            self.added = None
            self.committed = False
            self.refreshed = False

        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=None)

        def add(self, obj):
            self.added = obj

        async def commit(self):
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not be called on successful registration")

        async def refresh(self, obj):
            self.refreshed = True
            obj.id = 11

    db = FakeSession()
    user = await AuthService.register(
        db,
        RegisterRequest(
            invitation_code=code,
            email="user@example.com",
            password="StrongPass123!",
            confirm_password="StrongPass123!",
            verification_code="123456",
        ),
    )

    assert user.uid == 424242
    assert db.committed is True
    assert db.refreshed is True
    assert invitation_state[code]["consumed"] is True
    assert invitation_state[code]["used_by"] == 424242


@pytest.mark.asyncio
async def test_failed_registration_releases_consumed_invitation_code(monkeypatch):
    from admin_service.api.v1.endpoints.invitation import (
        GenerateInvitationCodeRequest,
        generate_invitation_codes,
    )
    from user_service.schemas import RegisterRequest
    from user_service.services.auth_service import AuthService

    invitation_state: dict[str, dict[str, object]] = {}

    async def fake_generate(*, db, created_by, quantity, expires_days, expires_at, max_uses, remark):
        del db, created_by, quantity, expires_days, expires_at, max_uses, remark
        code = "INVITE-E2E-ROLLBACK"
        invitation_state[code] = {"consumed": False, "used_by": None, "released": False}
        return [
            SimpleNamespace(
                id=2,
                code=code,
                status=0,
                expires_at=None,
                used_by=None,
                used_at=None,
                remark=None,
                created_at=datetime.now(),
            )
        ]

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.invitation.InvitationCodeService.generate",
        fake_generate,
    )
    generated = await generate_invitation_codes(
        request=GenerateInvitationCodeRequest(quantity=1, expires_days=7, max_uses=1),
        current_admin=SimpleNamespace(id=9001, uid=9001),
        db=object(),
    )
    code = generated.data.codes[0].code

    async def fake_verify_code(_db, _email, _code_value, _purpose):
        return None

    async def fake_consume_invitation(code_value, used_by_uid):
        invitation_state[code_value]["consumed"] = True
        invitation_state[code_value]["used_by"] = used_by_uid

    async def fake_release_invitation(code_value, used_by_uid):
        invitation_state[code_value]["released"] = True
        invitation_state[code_value]["used_by"] = used_by_uid
        return True

    monkeypatch.setattr(
        "user_service.services.auth_service.email_service.verify_code_or_raise",
        fake_verify_code,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AuthService._admin_gateway.consume_invitation_code",
        fake_consume_invitation,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.AuthService._admin_gateway.release_invitation_code",
        fake_release_invitation,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.generate_snowflake_id",
        lambda: 525252,
    )
    monkeypatch.setattr(
        "user_service.services.auth_service.hash_password",
        lambda password: f"hash:{password}",
    )

    class FailingSession:
        async def execute(self, _statement):
            return _ScalarResult(scalar_one_or_none=None)

        def add(self, _obj):
            return None

        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            return None

        async def refresh(self, _obj):
            raise AssertionError("refresh should not be called on failed commit")

    with pytest.raises(RuntimeError, match="commit failed"):
        await AuthService.register(
            FailingSession(),
            RegisterRequest(
                invitation_code=code,
                email="user@example.com",
                password="StrongPass123!",
                confirm_password="StrongPass123!",
                verification_code="123456",
            ),
        )

    assert invitation_state[code]["consumed"] is True
    assert invitation_state[code]["released"] is True
    assert invitation_state[code]["used_by"] == 525252


@pytest.mark.asyncio
async def test_router_key_crud_acceptance_flow(monkeypatch):
    from router_service.api.v1.endpoints.keys import (
        create_router_key,
        delete_router_key,
        list_router_keys,
        reveal_router_key,
        update_router_key,
    )
    from router_service.schemas import RouterApiKeyCreateRequest, RouterApiKeyUpdateRequest

    now = datetime.now()
    key_store: dict[int, dict] = {}

    async def fake_create_key(_db, *, owner_user_id, name):
        item = {
            "id": 1,
            "name": name,
            "token_preview": "sk-eucal-****",
            "is_active": True,
            "is_deleted": False,
            "billing_mode": "postpaid",
            "balance": None,
            "daily_quota_tokens": None,
            "monthly_quota_tokens": None,
            "daily_quota_cost": None,
            "monthly_quota_cost": None,
            "rate_limit_rpm": None,
            "last_used_at": None,
            "created_at": now,
            "updated_at": now,
            "owner_user_id": owner_user_id,
            "api_key": "sk-eucal-created",
        }
        key_store[item["id"]] = item
        return dict(item)

    async def fake_list_keys(_db, *, owner_user_id):
        return [
            {key: value for key, value in item.items() if key != "owner_user_id" and key != "api_key"}
            for item in key_store.values()
            if item["owner_user_id"] == owner_user_id and not item["is_deleted"]
        ]

    async def fake_update_owned_key(_db, *, owner_user_id, key_id, name, is_active):
        item = key_store.get(key_id)
        if item is None or item["owner_user_id"] != owner_user_id or item["is_deleted"]:
            return None
        if name is not None:
            item["name"] = name
        if is_active is not None:
            item["is_active"] = is_active
        item["updated_at"] = now
        return {key: value for key, value in item.items() if key not in {"owner_user_id", "api_key"}}

    async def fake_reveal_owned_key(_db, *, owner_user_id, key_id):
        item = key_store.get(key_id)
        if item is None or item["owner_user_id"] != owner_user_id or item["is_deleted"]:
            return None
        payload = dict(item)
        payload["api_key"] = "sk-eucal-created"
        return payload

    async def fake_delete_owned_key(_db, *, owner_user_id, key_id):
        item = key_store.get(key_id)
        if item is None or item["owner_user_id"] != owner_user_id:
            return False
        item["is_deleted"] = True
        return True

    monkeypatch.setattr("router_service.api.v1.endpoints.keys.RouterKeyAuthService.create_key", fake_create_key)
    monkeypatch.setattr("router_service.api.v1.endpoints.keys.RouterKeyAuthService.list_keys", fake_list_keys)
    monkeypatch.setattr(
        "router_service.api.v1.endpoints.keys.RouterKeyAuthService.update_owned_key",
        fake_update_owned_key,
    )
    monkeypatch.setattr(
        "router_service.api.v1.endpoints.keys.RouterKeyAuthService.reveal_owned_key",
        fake_reveal_owned_key,
    )
    monkeypatch.setattr(
        "router_service.api.v1.endpoints.keys.RouterKeyAuthService.delete_owned_key",
        fake_delete_owned_key,
    )

    user = SimpleNamespace(id=7, uid=77, email="user@example.com", status=1)
    created = await create_router_key(
        request=RouterApiKeyCreateRequest(name="default"),
        current_user=user,
        db=object(),
    )
    listed = await list_router_keys(current_user=user, db=object())
    updated = await update_router_key(
        key_id=1,
        request=RouterApiKeyUpdateRequest(name="renamed", is_active=False),
        current_user=user,
        db=object(),
    )
    revealed = await reveal_router_key(key_id=1, current_user=user, db=object())
    deleted = await delete_router_key(key_id=1, current_user=user, db=object())
    listed_after_delete = await list_router_keys(current_user=user, db=object())

    assert created.data.api_key == "sk-eucal-created"
    assert listed.data.items[0].name == "default"
    assert updated.data.name == "renamed"
    assert updated.data.is_active is False
    assert revealed.data.api_key == "sk-eucal-created"
    assert deleted.data.deleted is True
    assert listed_after_delete.data.items == []


@pytest.mark.asyncio
async def test_router_chat_completion_uses_testing_catalog_contract(monkeypatch):
    from router_service.api.v1.endpoints import openai_compat
    from router_service.schemas import RouterChatCompletionRequest
    from router_service.services import RouterKeyContext

    resolve_routes = AsyncMock(
        return_value={
            "items": [
                {
                    "provider_slug": "provider-a",
                    "provider_name": "Provider A",
                    "provider_model_name": "provider-a/demo-model",
                    "api_base_url": "https://example.com",
                    "encrypted_api_key": {"ciphertext": "c", "iv": "i", "tag": "t"},
                    "input_price_per_m": 1.0,
                    "output_price_per_m": 2.0,
                }
            ]
        }
    )
    reserve_usage = AsyncMock()
    settle_usage = AsyncMock()

    monkeypatch.setattr(
        "router_service.services.routing_service.TestingCatalogClientService.resolve_routes",
        resolve_routes,
    )
    monkeypatch.setattr(openai_compat.RouterBillingService, "reserve_usage", reserve_usage)
    monkeypatch.setattr(openai_compat.RouterBillingService, "settle_usage", settle_usage)
    monkeypatch.setattr(openai_compat, "_decrypt_provider_key", AsyncMock(return_value="secret"))
    monkeypatch.setattr(
        openai_compat.ProviderClientService,
        "chat_completion",
        AsyncMock(
            return_value={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": "demo-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hello back"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            }
        ),
    )
    monkeypatch.setattr(
        openai_compat.ProviderClientService,
        "normalize_payload",
        staticmethod(lambda payload: payload),
    )
    monkeypatch.setattr(
        openai_compat,
        "get_settings",
        lambda: SimpleNamespace(
            SMART_ROUTER_ENABLED=False,
            SMART_ROUTER_ALIAS="smart-router",
            SMART_ROUTER_FALLBACK_MODEL="",
            ROUTER_STREAM_TIMEOUT_SECONDS=60,
        ),
    )

    context = RouterKeyContext(
        key_id=1,
        owner_user_id=7,
        name="default",
        key_hash="hash",
        billing_mode="postpaid",
        balance=None,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=60,
    )
    response = await openai_compat.chat_completions(
        request=RouterChatCompletionRequest(
            model="demo-model",
            messages=[{"role": "user", "content": "hello"}],
        ),
        context=context,
        db=object(),
    )
    payload = json.loads(response.body)

    assert payload["model"] == "demo-model"
    assert payload["choices"][0]["message"]["content"] == "hello back"
    resolve_routes.assert_awaited_once()
    reserve_usage.assert_awaited_once()
    settle_usage.assert_awaited_once()
