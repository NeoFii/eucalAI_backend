"""Create provider_credentials table.

Stores AES-256-GCM encrypted upstream provider API keys.
The DDL was added to the baseline but not applied to existing databases.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260424_02_create_provider_credentials"
down_revision = "20260424_01_admin_uid_nanoid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables "
             "WHERE table_schema = DATABASE() "
             "AND table_name = 'provider_credentials'")
    )
    if result.scalar():
        return

    op.execute(
        """
        CREATE TABLE `provider_credentials` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `slug` VARCHAR(64) NOT NULL COMMENT 'Reference identifier',
            `provider_slug` VARCHAR(64) NOT NULL COMMENT 'Provider identifier e.g. autodl',
            `api_key_enc` JSON NOT NULL COMMENT 'AES-256-GCM encrypted {ciphertext,iv,tag}',
            `mask` VARCHAR(32) NOT NULL COMMENT 'Masked display e.g. sk-1****89ab',
            `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether credential is usable',
            `remark` VARCHAR(256) NULL COMMENT 'Optional note',
            `created_by` BIGINT NOT NULL COMMENT 'Admin who created this credential',
            `updated_by` BIGINT NULL COMMENT 'Admin who last updated this credential',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_provider_credentials_slug` (`slug`),
            CONSTRAINT `fk_provider_credentials_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT,
            CONSTRAINT `fk_provider_credentials_updated_by`
                FOREIGN KEY (`updated_by`) REFERENCES `admin_users` (`id`)
                ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Provider credentials'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `provider_credentials`")
