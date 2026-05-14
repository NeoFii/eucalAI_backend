"""Add audit_action_definitions table and FK on admin_audit_logs.action.

- Create audit_action_definitions registry table
- Seed with all known action codes
- Backfill any historical action values not in seed data
- Add FK constraint on admin_audit_logs.action
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260514_audit_action_defs"
down_revision = "20260514_enum_constraints"
branch_labels = None
depends_on = None

SEED_DATA = [
    # (code, label, category, resource_type)
    ("bootstrap_super_admin", "初始化超级管理员", "governance", "admin_user"),
    ("create_admin", "创建管理员", "governance", "admin_user"),
    ("enable_admin", "启用管理员", "governance", "admin_user"),
    ("disable_admin", "禁用管理员", "governance", "admin_user"),
    ("reset_admin_password", "重置管理员密码", "governance", "admin_user"),
    ("update_admin_role", "更新管理员角色", "governance", "admin_user"),
    ("admin_login_success", "管理员登录成功", "auth", "admin_user"),
    ("admin_login_failed", "管理员登录失败", "auth", "admin_user"),
    ("admin_login_locked", "管理员账号锁定", "auth", "admin_user"),
    ("admin_login_unlocked", "管理员账号解锁", "auth", "admin_user"),
    ("admin_change_password", "管理员修改密码", "auth", "admin_user"),
    ("enable_user", "启用用户", "user_management", "user"),
    ("disable_user", "禁用用户", "user_management", "user"),
    ("reset_user_password", "重置用户密码", "user_management", "user"),
    ("topup_user", "用户充值", "user_management", "user"),
    ("adjust_user_balance", "调整用户余额", "user_management", "user"),
    ("disable_user_api_key", "禁用用户API密钥", "user_management", "user"),
    ("enable_user_api_key", "启用用户API密钥", "user_management", "user"),
    ("update_user_rpm", "更新用户速率限制", "user_management", "user"),
    ("create_model_vendor", "创建模型厂商", "model_catalog", "model_vendor"),
    ("update_model_vendor", "更新模型厂商", "model_catalog", "model_vendor"),
    ("create_model_category", "创建模型分类", "model_catalog", "model_category"),
    ("update_model_category", "更新模型分类", "model_catalog", "model_category"),
    ("create_supported_model", "创建支持模型", "model_catalog", "supported_model"),
    ("update_supported_model", "更新支持模型", "model_catalog", "supported_model"),
    ("archive_supported_model", "归档支持模型", "model_catalog", "supported_model"),
    ("disable_supported_model", "归档支持模型", "model_catalog", "supported_model"),
    ("create_routing_config", "创建路由配置", "routing_config", "routing_config"),
    ("update_routing_config", "更新路由配置", "routing_config", "routing_config"),
    ("publish_routing_config", "发布路由配置", "routing_config", "routing_config"),
    ("rollback_routing_config", "回滚路由配置", "routing_config", "routing_config"),
    ("create_provider_credential", "创建供应商凭证", "routing_config", "routing_config"),
    ("update_provider_credential", "更新供应商凭证", "routing_config", "routing_config"),
    ("disable_provider_credential", "禁用供应商凭证", "routing_config", "routing_config"),
    ("force_disable_provider_credential", "强制禁用供应商凭证", "routing_config", "routing_config"),
    ("update_routing_setting", "更新路由设置", "routing_config", "routing_setting"),
    ("batch_update_routing_settings", "批量更新路由设置", "routing_config", "routing_setting"),
    ("generate_voucher_codes", "生成兑换码", "voucher", "voucher"),
    ("disable_voucher_code", "禁用兑换码", "voucher", "voucher"),
    ("create_pool", "创建资源池", "pool", "pool"),
    ("update_pool", "更新资源池", "pool", "pool"),
    ("disable_pool", "禁用资源池", "pool", "pool"),
    ("add_pool_model", "添加池模型", "pool", "pool_model"),
    ("update_pool_model", "更新池模型", "pool", "pool_model"),
    ("remove_pool_model", "移除池模型", "pool", "pool_model"),
    ("add_pool_account", "添加池账号", "pool", "pool_account"),
    ("update_pool_account", "更新池账号", "pool", "pool_account"),
    ("disable_pool_account", "禁用池账号", "pool", "pool_account"),
    ("sync_pool_models", "同步池模型", "pool", "pool"),
    ("check_pool_balances", "检查池余额", "pool", "pool"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create table
    op.create_table(
        "audit_action_definitions",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # 2. Insert seed data
    seed_codes = set()
    for i, (code, label, category, resource_type) in enumerate(SEED_DATA):
        seed_codes.add(code)
        conn.execute(sa.text(
            "INSERT INTO audit_action_definitions (code, label, category, resource_type, sort_order, created_at) "
            "VALUES (:code, :label, :category, :resource_type, :sort_order, NOW())"
        ), {"code": code, "label": label, "category": category, "resource_type": resource_type, "sort_order": i})

    # 3. Scan historical audit logs for any action values not in seed data
    result = conn.execute(sa.text(
        "SELECT DISTINCT action FROM admin_audit_logs"
    ))
    historical_actions = {row[0] for row in result}
    missing = historical_actions - seed_codes
    for code in sorted(missing):
        # Try to determine resource_type from existing logs
        rt_result = conn.execute(sa.text(
            "SELECT resource_type FROM admin_audit_logs WHERE action = :code LIMIT 1"
        ), {"code": code})
        rt_row = rt_result.first()
        resource_type = rt_row[0] if rt_row else "unknown"
        conn.execute(sa.text(
            "INSERT INTO audit_action_definitions (code, label, category, resource_type, sort_order, created_at) "
            "VALUES (:code, :label, :category, :resource_type, 999, NOW())"
        ), {"code": code, "label": code, "category": "unknown", "resource_type": resource_type})

    # 4. Add FK constraint
    op.create_foreign_key(
        "fk_audit_logs_action",
        "admin_audit_logs",
        "audit_action_definitions",
        ["action"],
        ["code"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_logs_action", "admin_audit_logs", type_="foreignkey")
    op.drop_table("audit_action_definitions")
