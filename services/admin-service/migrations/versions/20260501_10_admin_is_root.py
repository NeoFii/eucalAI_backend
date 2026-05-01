"""Add is_root flag to admin_users."""

from __future__ import annotations

from alembic import op

revision = "20260501_10_admin_is_root"
down_revision = "20260430_09_monetary_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `admin_users` ADD COLUMN `is_root` TINYINT(1) NOT NULL DEFAULT 0"
        " COMMENT '根管理员标记' AFTER `role`"
    )
    op.execute(
        "UPDATE `admin_users` SET `is_root` = 1"
        " WHERE `role` = 'super_admin' AND `created_by_admin_id` IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `admin_users` DROP COLUMN `is_root`")
