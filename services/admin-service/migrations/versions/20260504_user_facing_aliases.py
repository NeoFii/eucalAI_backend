"""Add user_facing_aliases routing setting.

Adds the `user_facing_aliases` row to `routing_settings`. This is a
comma-separated list of model aliases that the router-service accepts in the
`model` field of API requests. The default is just `auto` (the router_alias
itself); admins can add more entries (e.g. `auto,pro,fast`) to expose extra
public aliases without code changes.

Any model name not in this allowlist will be rejected by router-service with
HTTP 400 / `error_code=invalid_model`. The router_alias is automatically
treated as part of the allowlist by the runtime config normalizer, so this
seed value is just a convenient default.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260504_user_facing_aliases"
down_revision = "20260501_baseline"
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
                    'user_facing_aliases',
                    'auto',
                    'string',
                    'general',
                    '允许的入口别名',
                    '逗号分隔的别名列表;只有此列表中的值能作为 API 请求的 model 字段;router_alias 自动包含在内',
                    1
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM `routing_settings` WHERE `key` = 'user_facing_aliases'")
    )
