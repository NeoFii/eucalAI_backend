"""Admin audit service owned by the admin domain."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin_service.management_schemas import AdminAuditCategory
from admin_service.models import AdminAuditLog, AdminUser


class AdminAuditService:
    """Write and query admin audit log records."""

    GOVERNANCE_ACTIONS = (
        "bootstrap_super_admin",
        "create_admin",
        "enable_admin",
        "disable_admin",
        "reset_admin_password",
    )
    AUTH_ACTIONS = (
        "admin_login_success",
        "admin_login_failed",
        "admin_login_locked",
        "admin_login_unlocked",
    )
    CATEGORY_ACTIONS = {
        "governance": GOVERNANCE_ACTIONS,
        "auth": AUTH_ACTIONS,
    }

    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        actor_admin_id: int,
        target_admin_id: int | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        status: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditLog:
        audit_log = AdminAuditLog(
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(audit_log)
        await db.flush()
        return audit_log

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        category: AdminAuditCategory = "all",
        action: str | None = None,
        actor_uid: int | None = None,
        target_uid: int | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        actor_admin_id = None
        if actor_uid is not None:
            actor_result = await db.execute(select(AdminUser.id).where(AdminUser.uid == actor_uid))
            actor_admin_id = actor_result.scalar_one_or_none()
            if actor_admin_id is None:
                return [], 0

        target_admin_id = None
        if target_uid is not None:
            target_result = await db.execute(select(AdminUser.id).where(AdminUser.uid == target_uid))
            target_admin_id = target_result.scalar_one_or_none()
            if target_admin_id is None:
                return [], 0

        query = select(AdminAuditLog).options(
            selectinload(AdminAuditLog.actor_admin),
            selectinload(AdminAuditLog.target_admin),
        )
        count_query = select(func.count()).select_from(AdminAuditLog)

        if category != "all":
            category_actions = AdminAuditService.CATEGORY_ACTIONS[category]
            query = query.where(AdminAuditLog.action.in_(category_actions))
            count_query = count_query.where(AdminAuditLog.action.in_(category_actions))

        if action:
            query = query.where(AdminAuditLog.action == action)
            count_query = count_query.where(AdminAuditLog.action == action)
        if actor_admin_id is not None:
            query = query.where(AdminAuditLog.actor_admin_id == actor_admin_id)
            count_query = count_query.where(AdminAuditLog.actor_admin_id == actor_admin_id)
        if target_admin_id is not None:
            query = query.where(AdminAuditLog.target_admin_id == target_admin_id)
            count_query = count_query.where(AdminAuditLog.target_admin_id == target_admin_id)

        query = query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        total = int((await db.execute(count_query)).scalar() or 0)
        result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total
