"""Drop user_api_keys.rpm_limit — collapse to three tiers only.

The system's RPM management is intentionally limited to three tiers:
- Global default (admin-service `routing_settings.default_user_rpm`)
- Pool account (admin-service `pool_accounts.rpm_limit`)
- User (this service's `users.rpm_limit`)

The per-API-key override is being removed because it added a fourth tier
that complicates reasoning about effective RPM and was not part of the
product design. This migration drops the column added in
`20260429_01_add_api_key_rpm_limit`. Backend code that referenced it has
been removed in lockstep.
"""

from __future__ import annotations

from alembic import op

revision = "20260505_02_drop_api_key_rpm_limit"
down_revision = "20260505_01_add_user_rpm_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE `user_api_keys` DROP COLUMN `rpm_limit`")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `user_api_keys` "
        "ADD COLUMN `rpm_limit` INT NULL DEFAULT NULL "
        "COMMENT '每分钟请求上限，NULL=用全局默认' "
        "AFTER `allow_ips`"
    )
