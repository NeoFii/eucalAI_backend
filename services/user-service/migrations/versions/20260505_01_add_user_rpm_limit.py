"""Add rpm_limit column to users.

Adds a per-user RPM override. NULL means use the global default
(router-service `RATE_LIMIT_DEFAULT_USER_RPM`). The router-service prefers
this over the per-API-key `user_api_keys.rpm_limit`.
"""

from __future__ import annotations

from alembic import op

revision = "20260505_01_add_user_rpm_limit"
down_revision = "20260504_01_add_route_monitor_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `users` "
        "ADD COLUMN `rpm_limit` INT NULL DEFAULT NULL "
        "COMMENT '用户级每分钟请求上限，NULL=用全局默认' "
        "AFTER `total_tokens`"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `users` DROP COLUMN `rpm_limit`")
