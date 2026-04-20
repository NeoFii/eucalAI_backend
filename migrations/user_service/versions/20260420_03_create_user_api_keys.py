"""Create user_api_keys.

Stores per-user API keys used by router-service. key_hash is sha256 of the raw
key (for equality lookup); key_prefix is the first 8 plaintext chars for UI
display. quota_mode=1 unlimited / 2 limited; in limited mode quota_used is
enforced against quota_limit. See refactor/user-service.md §3.2.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_03_create_user_api_keys"
down_revision = "20260420_02_users_add_balance_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `user_api_keys` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `key_hash` VARCHAR(128) NOT NULL COMMENT 'SHA-256 of raw key',
            `key_prefix` VARCHAR(12) NOT NULL COMMENT 'First 8 plaintext chars for UI',
            `name` VARCHAR(100) NOT NULL COMMENT 'User-defined name',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=disabled 3=expired 4=exhausted',
            `quota_mode` TINYINT NOT NULL DEFAULT 1 COMMENT '1=unlimited 2=limited',
            `quota_limit` INT NOT NULL DEFAULT 0 COMMENT 'limited-mode cap (分)',
            `quota_used` INT NOT NULL DEFAULT 0 COMMENT 'cumulative spend via this key (分)',
            `allowed_models` TEXT NULL COMMENT 'comma-separated model names, NULL=all',
            `allow_ips` TEXT NULL COMMENT 'newline-separated CIDRs, NULL=all',
            `expires_at` DATETIME NULL COMMENT 'NULL = never expires',
            `last_used_at` DATETIME NULL COMMENT 'Last successful validation',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_user_api_keys_key_hash` (`key_hash`),
            KEY `idx_user_api_keys_user_id` (`user_id`),
            KEY `idx_user_api_keys_status` (`status`),
            CONSTRAINT `fk_user_api_keys_user_id`
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='User API keys'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `user_api_keys`")
