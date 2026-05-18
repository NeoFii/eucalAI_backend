"""API key CRUD and validation for api-service."""

from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
    ApiKeyDisabledException,
    ApiKeyExhaustedException,
    ApiKeyExpiredException,
    ApiKeyIpNotAllowedException,
    ApiKeyModelNotAllowedException,
    ApiKeyNotFoundException,
    UserDisabledException,
    ValidationException,
)
from api_service.common.utils.timezone import now
from api_service.core.config import settings
from api_service.models import UserApiKey
from api_service.repositories.api_key_repository import ApiKeyRepository
from api_service.repositories.user_repository import UserRepository
from api_service.common.utils.api_key_policy import is_ip_allowed, is_model_allowed

_KEY_ALPHABET = string.ascii_letters + string.digits


class ApiKeyService:
    """Manage user-owned API keys."""

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        name: str,
        quota_mode: int = UserApiKey.MODE_UNLIMITED,
        quota_limit: int = 0,
        allowed_models: str | None = None,
        allow_ips: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[UserApiKey, str]:
        repo = ApiKeyRepository(db)
        if await repo.count_for_user(user_id) >= settings.MAX_API_KEYS_PER_USER:
            raise ValidationException(detail="API Key 数量已达上限")

        if quota_mode not in {UserApiKey.MODE_UNLIMITED, UserApiKey.MODE_LIMITED}:
            raise ValidationException(detail="无效的配额模式")
        if quota_mode == UserApiKey.MODE_LIMITED and quota_limit <= 0:
            raise ValidationException(detail="限额模式下 quota_limit 必须大于 0")

        raw_key = "sk-" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(46))
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        api_key = UserApiKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=raw_key[:8],
            name=name,
            status=UserApiKey.STATUS_ACTIVE,
            quota_mode=quota_mode,
            quota_used=0,
            quota_limit=quota_limit if quota_mode == UserApiKey.MODE_LIMITED else 0,
            allowed_models=allowed_models,
            allow_ips=allow_ips,
            expires_at=expires_at,
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
        new_quota_limit: int | None = None,
        reset_quota_used: bool = False,
        allowed_models: str | None = None,
        allow_ips: str | None = None,
        expires_at: datetime | None = None,
        provided_fields: set[str],
    ) -> UserApiKey:
        api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
        if "name" in provided_fields and name is not None:
            api_key.name = name
        if "quota_limit" in provided_fields and new_quota_limit is not None:
            if api_key.quota_mode != UserApiKey.MODE_LIMITED or new_quota_limit <= 0:
                raise ValidationException(detail="仅限额模式支持更新 quota_limit")
            api_key.quota_limit = new_quota_limit
        if "allowed_models" in provided_fields:
            api_key.allowed_models = allowed_models
        if "allow_ips" in provided_fields:
            api_key.allow_ips = allow_ips
        if "expires_at" in provided_fields:
            api_key.expires_at = expires_at
        if reset_quota_used:
            api_key.quota_used = 0

        ApiKeyService._refresh_status(api_key)
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
        ApiKeyService._refresh_status(api_key)
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
        *,
        model: str | None = None,
        client_ip: str | None = None,
    ) -> UserApiKey:
        api_key = await ApiKeyRepository(db).get_by_hash(key_hash)
        if api_key is None:
            raise ApiKeyNotFoundException()

        user = await UserRepository(db).get_by_id(api_key.user_id)
        if user is None or user.status != 1:
            raise UserDisabledException()

        previous_status = api_key.status
        ApiKeyService._refresh_status(api_key)
        if api_key.status != previous_status:
            await db.commit()
        ApiKeyService._raise_for_validation_status(api_key)
        if model is not None and not is_model_allowed(api_key.allowed_models, model):
            raise ApiKeyModelNotAllowedException()
        if client_ip is not None and not is_ip_allowed(api_key.allow_ips, client_ip):
            raise ApiKeyIpNotAllowedException()

        api_key.last_used_at = now()
        await db.commit()
        return api_key

    @staticmethod
    def _refresh_status(api_key: UserApiKey) -> None:
        if api_key.status == UserApiKey.STATUS_DISABLED:
            return
        if api_key.expires_at and api_key.expires_at <= now():
            api_key.status = UserApiKey.STATUS_EXPIRED
            return
        if api_key.is_exhausted:
            api_key.status = UserApiKey.STATUS_EXHAUSTED
            return
        api_key.status = UserApiKey.STATUS_ACTIVE

    @staticmethod
    def _raise_for_validation_status(api_key: UserApiKey) -> None:
        if api_key.status == UserApiKey.STATUS_ACTIVE:
            return
        if api_key.status == UserApiKey.STATUS_DISABLED:
            raise ApiKeyDisabledException()
        if api_key.status == UserApiKey.STATUS_EXPIRED:
            raise ApiKeyExpiredException()
        if api_key.status == UserApiKey.STATUS_EXHAUSTED:
            raise ApiKeyExhaustedException()
        raise ApiKeyNotFoundException()

    @staticmethod
    async def verify_key_ownership(db: AsyncSession, key_id: int, user_id: int) -> UserApiKey:
        api_key = await ApiKeyRepository(db).get_owned_key(key_id, user_id)
        if api_key is None:
            raise ApiKeyNotFoundException()
        return api_key

    @staticmethod
    async def disable_all_for_user(db: AsyncSession, user_id: int) -> int:
        return await ApiKeyRepository(db).disable_all_for_user(user_id)
