"""Add rpm_limit column to user_api_keys."""

from __future__ import annotations

from alembic import op

revision = "20260429_01_add_api_key_rpm_limit"
down_revision = "20260428_02_add_provider_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `user_api_keys` "
        "ADD COLUMN `rpm_limit` INT NULL DEFAULT NULL "
        "COMMENT '每分钟请求上限，NULL=用全局默认' "
        "AFTER `allow_ips`"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `user_api_keys` DROP COLUMN `rpm_limit`")
