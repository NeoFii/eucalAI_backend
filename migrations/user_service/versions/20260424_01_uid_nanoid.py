"""Migrate uid columns from BIGINT (Snowflake) to VARCHAR(20) (NanoID).

Existing rows get new 10-character NanoID values.
"""

from __future__ import annotations

from alembic import op
from nanoid import generate
from sqlalchemy import text

revision = "20260424_01_uid_nanoid"
down_revision = "20260423_02_drop_invitation_release_outbox"
branch_labels = None
depends_on = None

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SIZE = 10


def _generate_uid() -> str:
    return generate(_ALPHABET, _SIZE)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Migrate users.uid: BIGINT -> VARCHAR(20)
    #    Drop unique key first, alter column, re-add unique key
    op.execute("ALTER TABLE `users` DROP INDEX `uk_users_uid`")
    op.execute(
        "ALTER TABLE `users` MODIFY COLUMN `uid` VARCHAR(20) NOT NULL "
        "COMMENT 'Public user UID (NanoID)'"
    )

    rows = conn.execute(text("SELECT id, uid FROM users")).fetchall()
    for row in rows:
        new_uid = _generate_uid()
        conn.execute(
            text("UPDATE users SET uid = :new_uid WHERE id = :id"),
            {"new_uid": new_uid, "id": row.id},
        )

    op.execute("ALTER TABLE `users` ADD UNIQUE KEY `uk_users_uid` (`uid`)")

    # 2. Migrate voucher_redemption_codes.created_by_admin_uid: BIGINT -> VARCHAR(20)
    op.execute("ALTER TABLE `voucher_redemption_codes` DROP INDEX `idx_voucher_codes_admin_uid`")
    op.execute(
        "ALTER TABLE `voucher_redemption_codes` MODIFY COLUMN `created_by_admin_uid` "
        "VARCHAR(20) NULL COMMENT 'Creator admin uid (NanoID)'"
    )
    op.execute(
        "ALTER TABLE `voucher_redemption_codes` ADD KEY "
        "`idx_voucher_codes_admin_uid` (`created_by_admin_uid`)"
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Revert voucher_redemption_codes
    op.execute("ALTER TABLE `voucher_redemption_codes` DROP INDEX `idx_voucher_codes_admin_uid`")
    op.execute(
        "ALTER TABLE `voucher_redemption_codes` MODIFY COLUMN `created_by_admin_uid` "
        "BIGINT NULL COMMENT 'Creator admin uid'"
    )
    op.execute(
        "ALTER TABLE `voucher_redemption_codes` ADD KEY "
        "`idx_voucher_codes_admin_uid` (`created_by_admin_uid`)"
    )

    # Revert users.uid (data will be lost — NanoID strings cannot be converted back)
    op.execute("ALTER TABLE `users` DROP INDEX `uk_users_uid`")
    op.execute(
        "ALTER TABLE `users` MODIFY COLUMN `uid` BIGINT NOT NULL "
        "COMMENT 'Public user UID'"
    )
    op.execute("ALTER TABLE `users` ADD UNIQUE KEY `uk_users_uid` (`uid`)")
