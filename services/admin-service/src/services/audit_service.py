"""Admin audit service owned by the admin domain."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import AdminAuditLog
from repositories import AdminAuditLogRepository, AdminUserRepository
from schemas.audit_log import AdminAuditCategory


class AdminAuditService:
    """Write and query admin audit log records."""

    GOVERNANCE_ACTIONS = (
        "bootstrap_super_admin",
        "create_admin",
        "enable_admin",
        "disable_admin",
        "reset_admin_password",
        "update_admin_role",
    )
    AUTH_ACTIONS = (
        "admin_login_success",
        "admin_login_failed",
        "admin_login_locked",
        "admin_login_unlocked",
        "admin_change_password",
    )
    CATEGORY_ACTIONS: dict[str, tuple[str, ...]] = {
        "governance": GOVERNANCE_ACTIONS,
        "auth": AUTH_ACTIONS,
        "user_management": (
            "enable_user",
            "disable_user",
            "reset_user_password",
            "topup_user",
            "adjust_user_balance",
            "disable_user_api_key",
            "enable_user_api_key",
            "update_user_rpm",
        ),
        "model_catalog": (
            "create_model_vendor",
            "update_model_vendor",
            "create_model_category",
            "update_model_category",
            "create_supported_model",
            "update_supported_model",
            "archive_supported_model",
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
            "update_routing_setting",
            "batch_update_routing_settings",
        ),
        "voucher": (
            "generate_voucher_codes",
            "disable_voucher_code",
        ),
        "pool": (
            "create_pool",
            "update_pool",
            "disable_pool",
            "add_pool_model",
            "update_pool_model",
            "remove_pool_model",
            "add_pool_account",
            "update_pool_account",
            "disable_pool_account",
            "sync_pool_models",
            "check_pool_balances",
        ),
    }

    ACTION_LABELS: dict[str, str] = {
        "bootstrap_super_admin": "初始化超级管理员",
        "create_admin": "创建管理员",
        "enable_admin": "启用管理员",
        "disable_admin": "禁用管理员",
        "reset_admin_password": "重置管理员密码",
        "update_admin_role": "更新管理员角色",
        "admin_login_success": "管理员登录成功",
        "admin_login_failed": "管理员登录失败",
        "admin_login_locked": "管理员账号锁定",
        "admin_login_unlocked": "管理员账号解锁",
        "admin_change_password": "管理员修改密码",
        "enable_user": "启用用户",
        "disable_user": "禁用用户",
        "reset_user_password": "重置用户密码",
        "topup_user": "用户充值",
        "adjust_user_balance": "调整用户余额",
        "disable_user_api_key": "禁用用户API密钥",
        "enable_user_api_key": "启用用户API密钥",
        "update_user_rpm": "更新用户速率限制",
        "create_model_vendor": "创建模型厂商",
        "update_model_vendor": "更新模型厂商",
        "create_model_category": "创建模型分类",
        "update_model_category": "更新模型分类",
        "create_supported_model": "创建支持模型",
        "update_supported_model": "更新支持模型",
        "archive_supported_model": "归档支持模型",
        "disable_supported_model": "归档支持模型",
        "create_routing_config": "创建路由配置",
        "update_routing_config": "更新路由配置",
        "publish_routing_config": "发布路由配置",
        "rollback_routing_config": "回滚路由配置",
        "create_provider_credential": "创建供应商凭证",
        "update_provider_credential": "更新供应商凭证",
        "disable_provider_credential": "禁用供应商凭证",
        "force_disable_provider_credential": "强制禁用供应商凭证",
        "update_routing_setting": "更新路由设置",
        "batch_update_routing_settings": "批量更新路由设置",
        "generate_voucher_codes": "生成兑换码",
        "disable_voucher_code": "禁用兑换码",
        "create_pool": "创建资源池",
        "update_pool": "更新资源池",
        "disable_pool": "禁用资源池",
        "add_pool_model": "添加池模型",
        "update_pool_model": "更新池模型",
        "remove_pool_model": "移除池模型",
        "add_pool_account": "添加池账号",
        "update_pool_account": "更新池账号",
        "disable_pool_account": "禁用池账号",
        "sync_pool_models": "同步池模型",
        "check_pool_balances": "检查池余额",
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
    async def record_auto(
        db: AsyncSession,
        *,
        actor_admin_id: int,
        target_admin_id: int | None = None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        status: str = "success",
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditLog:
        """Record with ip/user_agent auto-filled from request context if not provided."""
        from common.request_context import get_request_ip, get_request_user_agent

        return await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            ip_address=ip_address or get_request_ip(),
            user_agent=user_agent or get_request_user_agent(),
        )

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
