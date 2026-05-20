"""API key CRUD and validation for api-service."""

from __future__ import annotations

import hashlib
import secrets
import string

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import (
    ApiKeyDisabledException,
    ApiKeyNotFoundException,
    UserDisabledException,
    ValidationException,
)
from app.common.utils.timezone import now
from app.core.config import settings
from app.model import UserApiKey
from app.repository.api_key_repository import ApiKeyRepository
from app.repository.user_repository import UserRepository

_KEY_ALPHABET = string.ascii_letters + string.digits


class ApiKeyService:
    """Manage user-owned API keys."""

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        name: str,
    ) -> tuple[UserApiKey, str]:
        repo = ApiKeyRepository(db)
        if await repo.count_for_user(user_id) >= settings.MAX_API_KEYS_PER_USER:
            raise ValidationException(detail="API Key 数量已达上限")

        raw_key = "sk-" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(46))
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        api_key = UserApiKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=raw_key[:8],
            name=name,
            status=UserApiKey.STATUS_ACTIVE,
        )
        repo.add(api_key)
        await db.commit()
        await db.refresh(api_key)
        return api_key, raw_key

    @staticmethod
    async def list(db: AsyncSession, user_id: int) -> list[UserApiKey]:
        return await ApiKeyRepository(db).list_for_user(user_id)

    @staticmethod
    async def update(
        db: AsyncSession,
        key_id: int,
        user_id: int,
        *,
        name: str | None = None,
    ) -> UserApiKey:
        api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
        if name is not None:
            api_key.name = name
        await db.commit()
        await db.refresh(api_key)
        return api_key

    @staticmethod
    async def disable(db: AsyncSession, key_id: int, user_id: int) -> None:
        api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
        api_key.status = UserApiKey.STATUS_DISABLED
        await db.commit()

    @staticmethod
    async def enable(db: AsyncSession, key_id: int, user_id: int) -> None:
        api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
        api_key.status = UserApiKey.STATUS_ACTIVE
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, key_id: int, user_id: int) -> None:
        api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
        api_key.deleted_at = now()
        await db.commit()

    @staticmethod
    async def validate_by_hash(
        db: AsyncSession,
        key_hash: str,
    ) -> UserApiKey:
        api_key = await ApiKeyRepository(db).get_by_hash(key_hash)
        if api_key is None:
            raise ApiKeyNotFoundException()

        user = await UserRepository(db).get_by_id(api_key.user_id)
        if user is None or user.status != 1:
            raise UserDisabledException()

        if api_key.status != UserApiKey.STATUS_ACTIVE:
            raise ApiKeyDisabledException()

        api_key.last_used_at = now()
        await db.commit()
        return api_key

    @staticmethod
    async def verify_key_ownership(db: AsyncSession, key_id: int, user_id: int) -> UserApiKey:
        api_key = await ApiKeyRepository(db).get_owned_key(key_id, user_id)
        if api_key is None:
            raise ApiKeyNotFoundException()
        return api_key

    @staticmethod
    async def disable_all_for_user(db: AsyncSession, user_id: int) -> int:
        return await ApiKeyRepository(db).disable_all_for_user(user_id)
