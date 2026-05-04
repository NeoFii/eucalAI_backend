"""Seed system_rpm_cap rate-limit setting + refresh default_user_rpm description.

Adds a `system_rpm_cap` row in `routing_settings` (group=`rate_limits`).

Conceptually distinct from `default_user_rpm`:

- `default_user_rpm` — the value snapshotted into `users.rpm_limit` at
  registration. Each new user starts at this number; admins can later override
  per user. Editing it does NOT retroactively change existing users.

- `system_rpm_cap` — a system-wide hard upper bound. The router enforces
  `min(user.rpm_limit, system_rpm_cap)`. Lets ops cap blast-radius without
  having to walk every user row.

Two layers, two settings, both managed in admin-service. router-service polls
both via the routing-config endpoint (~60s refresh).

Initial value 1000 is intentionally generous so existing user RPMs (≤ 100)
aren't unintentionally clamped by this cap going live. Admins can tighten
post-deploy.

Also updates the description of `default_user_rpm` to reflect the new
two-tier (global default → user) model since the per-API-key tier is gone.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260505_02_system_rpm_cap"
down_revision = "20260505_default_user_rpm"
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
                    'system_rpm_cap',
                    '1000',
                    'int',
                    'rate_limits',
                    '系统 RPM 硬上限',
                    '系统级 RPM 硬上限。任何用户的实际 RPM 不会超过此值，即使其个人 RPM 设得更高。修改后约 60 秒内全节点生效。',
                    1
                )
            """
        )
    )
    # Refresh the description of default_user_rpm to drop the per-API-key tier.
    conn.execute(
        text(
            """
            UPDATE `routing_settings`
            SET
                `label` = '用户默认 RPM',
                `description` = '新注册用户的初始 RPM（次/分钟）。注册时快照写入用户。修改后仅影响后续注册的新用户。',
                `sort_order` = 0
            WHERE `key` = 'default_user_rpm'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM `routing_settings` WHERE `key` = 'system_rpm_cap'")
    )
