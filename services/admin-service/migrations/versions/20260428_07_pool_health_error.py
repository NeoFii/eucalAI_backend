"""Add last_health_check_error to pool_accounts."""

from __future__ import annotations

from alembic import op

revision = "20260428_07_pool_health_error"
down_revision = "20260428_06_add_cached_input_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `pool_accounts` "
        "ADD COLUMN `last_health_check_error` VARCHAR(512) NULL "
        "COMMENT '上次健康检查错误信息' "
        "AFTER `last_checked_at`"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `pool_accounts` DROP COLUMN `last_health_check_error`"
    )
