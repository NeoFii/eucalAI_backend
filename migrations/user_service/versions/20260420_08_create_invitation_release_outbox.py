"""Create invitation_release_outbox.

Used by the new registration flow to compensate if admin-service invitation
consumption succeeded but the local user-insert transaction rolled back. The
arq worker scans and retries with exponential back-off. See
refactor/user-service.md §5.5.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_08_create_invitation_release_outbox"
down_revision = "20260420_07_create_usage_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `invitation_release_outbox` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `code` VARCHAR(64) NOT NULL COMMENT 'Invitation code to release',
            `used_by_uid` BIGINT NOT NULL COMMENT 'Snowflake uid of the failed registrant',
            `retry_count` INT NOT NULL DEFAULT 0 COMMENT 'Worker retry counter',
            `last_error` VARCHAR(255) NULL COMMENT 'Last worker error message',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            KEY `idx_invitation_release_outbox_retry` (`retry_count`, `updated_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Compensation outbox for failed invitation-code releases'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `invitation_release_outbox`")
