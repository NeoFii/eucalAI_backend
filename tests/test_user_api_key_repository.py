"""Repository- and schema-level tests for user-service API key refactor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        if isinstance(self.value, list):
            return SimpleNamespace(all=lambda: self.value)
        return SimpleNamespace(all=lambda: [self.value] if self.value is not None else [])


def test_keys_schema_module_exports_current_contract_types():
    from user_service.schemas.keys import ApiKeyCreateRequest, ApiKeyItem, ApiKeyUpdateRequest

    assert ApiKeyCreateRequest is not None
    assert ApiKeyUpdateRequest is not None
    assert ApiKeyItem is not None


@pytest.mark.asyncio
async def test_api_key_repository_list_active_keys_filters_soft_deleted_rows():
    from user_service.repositories.api_key_repository import ApiKeyRepository

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult([])

    db = FakeSession()
    repo = ApiKeyRepository(db)

    items = await repo.list_for_user(user_id=10)

    assert items == []
    assert "user_api_keys.deleted_at IS NULL" in str(db.statements[0])


@pytest.mark.asyncio
async def test_api_key_repository_get_owned_key_filters_soft_deleted_rows():
    from user_service.repositories.api_key_repository import ApiKeyRepository

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return ScalarResult(None)

    db = FakeSession()
    repo = ApiKeyRepository(db)

    item = await repo.get_owned_key(key_id=101, user_id=10)

    assert item is None
    assert "user_api_keys.deleted_at IS NULL" in str(db.statements[0])


def test_policy_module_exports_active_user_guard():
    from user_service.policies import require_active_user

    assert require_active_user is not None
