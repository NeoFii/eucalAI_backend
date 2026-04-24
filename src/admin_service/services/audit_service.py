"""Admin audit service owned by the admin domain."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.models import AdminAuditLog
from admin_service.repositories import AdminAuditLogRepository, AdminUserRepository
from admin_service.schemas.audit_log import AdminAuditCategory


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
        "admin_change_password",
    )
    CATEGORY_ACTIONS = {
        "governance": GOVERNANCE_ACTIONS,
        "auth": AUTH_ACTIONS,
        "user_management": (
            "enable_user",
            "disable_user",
            "reset_user_password",
            "topup_user",
            "adjust_user_balance",
            "disable_user_api_key",
        ),
        "model_catalog": (
            "create_model_vendor",
            "update_model_vendor",
            "create_model_category",
            "update_model_category",
            "create_supported_model",
            "update_supported_model",
            "disable_supported_model",
        ),
        "routing_config": (
            "create_routing_config",
            "update_routing_config",
            "publish_routing_config",
            "rollback_routing_config",
            "create_provider_credential",
            "update_provider_credential",
            "disable_provider_credential",
            "force_disable_provider_credential",
        ),
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
        AdminAuditLogRepository(db).add(audit_log)
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
        actor_uid: str | None = None,
        target_uid: str | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        actor_admin_id = None
        if actor_uid is not None:
            actor_admin_id = await AdminUserRepository(db).get_id_by_uid(actor_uid)
            if actor_admin_id is None:
                return [], 0

        target_admin_id = None
        if target_uid is not None:
            target_admin_id = await AdminUserRepository(db).get_id_by_uid(target_uid)
            if target_admin_id is None:
                return [], 0

        category_actions = None
        if category != "all":
            category_actions = AdminAuditService.CATEGORY_ACTIONS[category]

        return await AdminAuditLogRepository(db).list_logs(
            page=page,
            page_size=page_size,
            actions=category_actions,
            action=action,
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
        )
