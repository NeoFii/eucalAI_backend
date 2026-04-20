"""Drop user_active_sessions zombie table.

The table was designed for a "one active refresh session per user" mapping,
but the application never read or wrote it (all session lookups go through
user_sessions). Dropping it removes dead state and unblocks balance/api-key
model work that will land on the same metadata.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_01_drop_user_active_sessions"
down_revision = "20260313_02_user_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `user_active_sessions`")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `user_active_sessions` (
            `user_id` BIGINT NOT NULL COMMENT 'User id',
            `session_id` BIGINT NOT NULL COMMENT 'Current active session id',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`user_id`),
            UNIQUE KEY `uk_user_active_sessions_session_id` (`session_id`),
            CONSTRAINT `fk_user_active_sessions_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_user_active_sessions_session_id`
                FOREIGN KEY (`session_id`) REFERENCES `user_sessions` (`session_id`)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='One active session per user'
        """
    )
