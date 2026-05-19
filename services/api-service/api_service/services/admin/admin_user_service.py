"""Admin end-user management service — proxy elimination layer.

Replaces UserManagementGateway HTTP calls with direct Phase 4 service /
Phase 3 repository calls. Class name is AdminEndUserService (NOT
AdminUserService — Pitfall 3 avoidance; AdminAccountService is the
admin-on-admin CRUD class from Plan 05-02).

D-02a: Phase 4 service signatures are NOT modified. No acting_admin_id
parameter is plumbed into Phase 4 services — audit happens at the
controller layer via inline AdminAuditService.record + db.commit().
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.infra.db.query import ListParams
from api_service.common.security.password import hash_password_async
from api_service.models import User
from api_service.repositories.user_repository import UserRepository
from api_service.services.api_key_service import ApiKeyService
from api_service.services.auth_service import AuthService
from api_service.services.balance_service import BalanceService
from api_service.services.usage_stat_service import UsageStatService

logger = logging.getLogger(__name__)


class _UserNotFound(Exception):
    """Raised when target_uid cannot be resolved."""


async def _resolve_user(db: AsyncSession, target_uid: str) -> User:
    """Resolve user_uid -> User or raise."""
    user = await UserRepository(db).get_by_uid(target_uid)
    if user is None:
        raise _UserNotFound(f"User not found: {target_uid}")
    return user


class AdminEndUserService:
    """14 staticmethods mapping 1:1 to source UserManagementGateway methods."""

    @staticmethod
    async def list_users(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: int | None = None,
    ) -> tuple[list[User], int]:
        return await UserRepository(db).list_users(
            page=page, page_size=page_size, search=search, status=status,
        )

    @staticmethod
    async def get_user_detail(db: AsyncSession, *, target_uid: str) -> dict[str, Any]:
        user = await _resolve_user(db, target_uid)
        return {
            "uid": user.uid,
            "email": user.email,
            "status": user.status,
            "email_verified_at": user.email_verified_at,
            "last_login_at": user.last_login_at,
            "last_login_ip": getattr(user, "last_login_ip", None),
            "balance": int(getattr(user, "balance", 0) or 0),
            "frozen_amount": int(getattr(user, "frozen_amount", 0) or 0),
            "used_amount": int(getattr(user, "used_amount", 0) or 0),
            "total_requests": int(getattr(user, "total_requests", 0) or 0),
            "total_tokens": int(getattr(user, "total_tokens", 0) or 0),
            "rpm_limit": user.rpm_limit,
            "default_rpm": getattr(user, "default_rpm", 0),
            "current_tpm": getattr(user, "current_tpm", 0),
            "created_at": user.created_at,
            "updated_at": getattr(user, "updated_at", None),
        }

    @staticmethod
    async def update_user_status(
        db: AsyncSession, *, target_uid: str, status: int,
    ) -> dict[str, Any]:
        user = await _resolve_user(db, target_uid)
        before_status = user.status
        user.status = status
        return {"before_status": before_status, "after_status": status}

    @staticmethod
    async def reset_user_password(
        db: AsyncSession, *, target_uid: str, new_password: str,
    ) -> User:
        user = await _resolve_user(db, target_uid)
        user.password_hash = await hash_password_async(new_password)
        # T-5-07: revoke ALL active sessions for the target user
        await AuthService._revoke_all_user_sessions(db, user.id)
        return user

    @staticmethod
    async def topup_user(
        db: AsyncSession,
        *,
        target_uid: str,
        amount: int,
        operator_admin: Any,
        remark: str | None = None,
    ) -> dict[str, Any]:
        user = await _resolve_user(db, target_uid)
        # Generate a unique order_no for admin topup
        import time
        order_no = f"admin_topup_{operator_admin.uid}_{int(time.time() * 1000)}"
        await BalanceService.topup(
            db,
            user_id=int(user.id),
            amount=amount,
            order_no=order_no,
            operator_id=str(operator_admin.uid),
            remark=remark or "",
        )
        return {"order_no": order_no}

    @staticmethod
    async def adjust_user_balance(
        db: AsyncSession,
        *,
        target_uid: str,
        delta: int,
        operator_admin: Any,
        remark: str | None = None,
    ) -> None:
        user = await _resolve_user(db, target_uid)
        await BalanceService.admin_adjust(
            db,
            user_id=int(user.id),
            amount=delta,
            operator_id=str(operator_admin.uid),
            remark=remark or "",
        )

    @staticmethod
    async def update_user_rpm(
        db: AsyncSession, *, target_uid: str, rpm_limit: int | None,
    ) -> dict[str, Any]:
        user = await _resolve_user(db, target_uid)
        before_rpm = user.rpm_limit
        repo = UserRepository(db)
        await repo.update_rpm_limit(int(user.id), rpm_limit)
        return {"before_rpm_limit": before_rpm, "after_rpm_limit": rpm_limit}

    @staticmethod
    async def list_user_transactions(
        db: AsyncSession, *, target_uid: str, page: int = 1, page_size: int = 20,
    ) -> tuple[list, int]:
        user = await _resolve_user(db, target_uid)
        result = await BalanceService.list_transactions(
            db,
            user_id=int(user.id),
            params=ListParams(page=page, page_size=page_size),
        )
        return result.items, result.total

    @staticmethod
    async def list_user_api_keys(db: AsyncSession, *, target_uid: str) -> list:
        user = await _resolve_user(db, target_uid)
        return await ApiKeyService.list(db, int(user.id))

    @staticmethod
    async def disable_user_api_key(
        db: AsyncSession, *, target_uid: str, key_id: int,
    ) -> None:
        user = await _resolve_user(db, target_uid)
        await ApiKeyService.disable(db, key_id, int(user.id))

    @staticmethod
    async def enable_user_api_key(
        db: AsyncSession, *, target_uid: str, key_id: int,
    ) -> None:
        user = await _resolve_user(db, target_uid)
        await ApiKeyService.enable(db, key_id, int(user.id))

    @staticmethod
    async def list_user_usage_logs(
        db: AsyncSession,
        *,
        target_uid: str | None = None,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        model_name: str | None = None,
        request_id: str | None = None,
        api_key_id: int | None = None,
        start=None,
        end=None,
    ) -> tuple[list, int]:
        resolved_user_id = user_id
        if target_uid:
            user = await _resolve_user(db, target_uid)
            resolved_user_id = int(user.id)
        result = await UsageStatService.list_usage_logs(
            db,
            params=ListParams(page=page, page_size=page_size),
            user_id=resolved_user_id,
            model_name=model_name,
            request_id=request_id,
            api_key_id=api_key_id,
        )
        return result.items, result.total

    @staticmethod
    async def list_user_usage_stats(
        db: AsyncSession,
        *,
        target_uid: str | None = None,
        user_id: int | None = None,
        model_name: str | None = None,
        api_key_id: int | None = None,
        start=None,
        end=None,
    ) -> list:
        resolved_user_id = user_id
        if target_uid:
            user = await _resolve_user(db, target_uid)
            resolved_user_id = int(user.id)
        result = await UsageStatService.get_all_stats(
            db,
            user_id=resolved_user_id,
            model_name=model_name,
            api_key_id=api_key_id,
        )
        return result

    @staticmethod
    async def get_user_usage_analytics(
        db: AsyncSession,
        *,
        target_uid: str,
        range_name: str | None = None,
        start=None,
        end=None,
        api_key_id: int | None = None,
    ) -> dict:
        user = await _resolve_user(db, target_uid)
        result = await UsageStatService.get_usage_analytics(
            db,
            user_id=int(user.id),
            range_name=range_name,
            start=start,
            end=end,
            api_key_id=api_key_id,
        )
        return result


__all__ = ["AdminEndUserService"]
