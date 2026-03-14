"""Router API key auth service."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.crypto import decrypt_api_key, encrypt_api_key
from router_service.config import get_settings
from router_service.models import RouterAPIKey
from router_service.services.identity_client import IdentityClientService


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _mask_api_key(raw_key: str) -> str:
    if len(raw_key) <= 16:
        return raw_key
    return f"{raw_key[:12]}...{raw_key[-4:]}"


@dataclass
class RouterKeyContext:
    """Resolved router key context."""

    key_id: int
    owner_user_id: int
    name: str
    key_hash: str
    billing_mode: str
    balance: float | None
    daily_quota_tokens: int | None
    monthly_quota_tokens: int | None
    daily_quota_cost: float | None
    monthly_quota_cost: float | None
    rate_limit_rpm: int | None


class RouterKeyAuthService:
    """User-facing API key CRUD and router auth helpers."""

    @staticmethod
    def _encrypt_raw_key(raw_key: str) -> str:
        settings = get_settings()
        encrypted = encrypt_api_key(raw_key, settings.router_secret_master_key)
        return json.dumps(encrypted, separators=(",", ":"))

    @staticmethod
    def _decrypt_raw_key(payload: str | None) -> str | None:
        if not payload:
            return None
        settings = get_settings()
        encrypted = json.loads(payload)
        return decrypt_api_key(
            encrypted["ciphertext"],
            encrypted["iv"],
            encrypted["tag"],
            settings.router_secret_master_key,
        )

    @staticmethod
    def generate_raw_key() -> str:
        settings = get_settings()
        return f"{settings.ROUTER_KEY_PREFIX}{secrets.token_hex(16)}"

    @staticmethod
    async def create_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        name: str,
    ) -> dict[str, Any]:
        raw_key = RouterKeyAuthService.generate_raw_key()
        key_hash = _hash_api_key(raw_key)
        settings = get_settings()
        item = RouterAPIKey(
            owner_user_id=owner_user_id,
            name=name.strip(),
            key_hash=key_hash,
            key_ciphertext=RouterKeyAuthService._encrypt_raw_key(raw_key),
            token_preview=_mask_api_key(raw_key),
            is_active=True,
            is_deleted=False,
            billing_mode=settings.ROUTER_DEFAULT_BILLING_MODE,
        )
        db.add(item)
        await db.flush()
        await db.commit()
        await db.refresh(item)
        payload = RouterKeyAuthService.serialize_key(item)
        payload["api_key"] = raw_key
        return payload

    @staticmethod
    async def list_keys(db: AsyncSession, *, owner_user_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(RouterAPIKey)
            .where(RouterAPIKey.owner_user_id == owner_user_id)
            .where(RouterAPIKey.is_deleted.is_(False))
            .order_by(RouterAPIKey.id.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [RouterKeyAuthService.serialize_key(item) for item in rows]

    @staticmethod
    async def get_owned_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        key_id: int,
    ) -> RouterAPIKey | None:
        stmt = (
            select(RouterAPIKey)
            .where(RouterAPIKey.id == key_id)
            .where(RouterAPIKey.owner_user_id == owner_user_id)
            .where(RouterAPIKey.is_deleted.is_(False))
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def update_owned_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        key_id: int,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any] | None:
        item = await RouterKeyAuthService.get_owned_key(
            db,
            owner_user_id=owner_user_id,
            key_id=key_id,
        )
        if item is None:
            return None
        if name is not None:
            item.name = name.strip()
        if is_active is not None:
            item.is_active = bool(is_active)
        await db.flush()
        await db.commit()
        await db.refresh(item)
        return RouterKeyAuthService.serialize_key(item)

    @staticmethod
    async def deactivate_owned_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        key_id: int,
    ) -> bool:
        item = await RouterKeyAuthService.get_owned_key(
            db,
            owner_user_id=owner_user_id,
            key_id=key_id,
        )
        if item is None:
            return False
        item.is_active = False
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def delete_owned_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        key_id: int,
    ) -> bool:
        item = await RouterKeyAuthService.get_owned_key(
            db,
            owner_user_id=owner_user_id,
            key_id=key_id,
        )
        if item is None:
            return False
        item.is_active = False
        item.is_deleted = True
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def reveal_owned_key(
        db: AsyncSession,
        *,
        owner_user_id: int,
        key_id: int,
    ) -> dict[str, Any] | None:
        item = await RouterKeyAuthService.get_owned_key(
            db,
            owner_user_id=owner_user_id,
            key_id=key_id,
        )
        if item is None:
            return None
        raw_key = RouterKeyAuthService._decrypt_raw_key(item.key_ciphertext)
        if not raw_key:
            raise ValueError("Router API key was created before secure reveal support")
        payload = RouterKeyAuthService.serialize_key(item)
        payload["api_key"] = raw_key
        return payload

    @staticmethod
    async def verify_key(db: AsyncSession, raw_key: str) -> RouterKeyContext | None:
        key_hash = _hash_api_key(raw_key)
        stmt = (
            select(RouterAPIKey)
            .where(RouterAPIKey.key_hash == key_hash)
            .where(RouterAPIKey.is_active.is_(True))
            .where(RouterAPIKey.is_deleted.is_(False))
            .limit(1)
        )
        item = (await db.execute(stmt)).scalar_one_or_none()
        if item is None:
            return None

        user = await IdentityClientService.fetch_user_by_id(int(item.owner_user_id))
        if user is None or user.status != 1:
            return None

        item.last_used_at = datetime.utcnow()
        await db.flush()
        return RouterKeyContext(
            key_id=int(item.id),
            owner_user_id=int(user.id),
            name=item.name,
            key_hash=item.key_hash,
            billing_mode=(item.billing_mode or "postpaid"),
            balance=float(item.balance) if item.balance is not None else None,
            daily_quota_tokens=item.daily_quota_tokens,
            monthly_quota_tokens=item.monthly_quota_tokens,
            daily_quota_cost=float(item.daily_quota_cost) if item.daily_quota_cost is not None else None,
            monthly_quota_cost=float(item.monthly_quota_cost) if item.monthly_quota_cost is not None else None,
            rate_limit_rpm=item.rate_limit_rpm,
        )

    @staticmethod
    def serialize_key(item: RouterAPIKey) -> dict[str, Any]:
        return {
            "id": int(item.id),
            "name": item.name,
            "token_preview": item.token_preview,
            "is_active": bool(item.is_active),
            "is_deleted": bool(item.is_deleted),
            "billing_mode": item.billing_mode,
            "balance": float(item.balance) if item.balance is not None else None,
            "daily_quota_tokens": item.daily_quota_tokens,
            "monthly_quota_tokens": item.monthly_quota_tokens,
            "daily_quota_cost": float(item.daily_quota_cost) if item.daily_quota_cost is not None else None,
            "monthly_quota_cost": float(item.monthly_quota_cost) if item.monthly_quota_cost is not None else None,
            "rate_limit_rpm": item.rate_limit_rpm,
            "last_used_at": item.last_used_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
