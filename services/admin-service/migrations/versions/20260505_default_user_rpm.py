"""Seed default_user_rpm rate-limit setting.

Adds a `default_user_rpm` row in `routing_settings` (group=`rate_limits`).
This is the global default per-user requests-per-minute limit applied when:
- `users.rpm_limit` is NULL (no per-user override), AND
- `user_api_keys.rpm_limit` is NULL (no per-key override)

router-service reads it from the runtime config (polled from admin-service)
so changes propagate without restart. user-service also exposes the current
value to user/admin UIs so they can show "X (默认)" labels.

Initial value 20 mirrors the legacy env-bound `RATE_LIMIT_DEFAULT_USER_RPM`,
keeping behaviour unchanged immediately after migration.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260505_default_user_rpm"
down_revision = "20260504_user_facing_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT IGNORE INTO `routing_settings`
                (`key`, `value`, `value_type`, `group_name`, `label`, `description`, `sort_order`)
            VALUES
                (
                    'default_user_rpm',
                    '20',
                    'int',
                    'rate_limits',
                    '全局默认 RPM',
                    '当用户和 API Key 都未单独设置 RPM 时使用的默认值（次/分钟）。优先级：API Key < 用户 < 全局默认。修改后约 60 秒内全节点生效。',
                    0
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM `routing_settings` WHERE `key` = 'default_user_rpm'")
    )
