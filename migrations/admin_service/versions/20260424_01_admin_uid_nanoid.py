"""Migrate admin_users.uid from BIGINT (Snowflake) to VARCHAR(20) (NanoID).

Existing rows get new 10-character NanoID values.
"""

from __future__ import annotations

from alembic import op
from nanoid import generate
from sqlalchemy import text

revision = "20260424_01_admin_uid_nanoid"
down_revision = "20260423_02_drop_invitation_codes"
branch_labels = None
depends_on = None

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SIZE = 10


def _generate_uid() -> str:
    return generate(_ALPHABET, _SIZE)


def upgrade() -> None:
    conn = op.get_bind()

    op.execute("ALTER TABLE `admin_users` DROP INDEX `uk_admin_users_uid`")
    op.execute(
        "ALTER TABLE `admin_users` MODIFY COLUMN `uid` VARCHAR(20) NOT NULL "
        "COMMENT 'Public admin UID (NanoID)'"
    )

    rows = conn.execute(text("SELECT id, uid FROM admin_users")).fetchall()
    for row in rows:
        new_uid = _generate_uid()
        conn.execute(
            text("UPDATE admin_users SET uid = :new_uid WHERE id = :id"),
            {"new_uid": new_uid, "id": row.id},
        )

    op.execute("ALTER TABLE `admin_users` ADD UNIQUE KEY `uk_admin_users_uid` (`uid`)")


def downgrade() -> None:
    op.execute("ALTER TABLE `admin_users` DROP INDEX `uk_admin_users_uid`")
    op.execute(
        "ALTER TABLE `admin_users` MODIFY COLUMN `uid` BIGINT NOT NULL "
        "COMMENT 'Public admin UID'"
    )
    op.execute("ALTER TABLE `admin_users` ADD UNIQUE KEY `uk_admin_users_uid` (`uid`)")
