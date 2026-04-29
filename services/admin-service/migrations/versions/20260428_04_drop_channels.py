"""Drop legacy channel tables replaced by pool system."""

from __future__ import annotations

from alembic import op

revision = "20260428_04_drop_channels"
down_revision = "20260428_03_pool_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `channel_model_abilities`")
    op.execute("DROP TABLE IF EXISTS `api_channels`")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `api_channels` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `slug` VARCHAR(64) NOT NULL,
            `name` VARCHAR(128) NOT NULL,
            `provider_slug` VARCHAR(64) NOT NULL,
            `api_key_enc` JSON NOT NULL,
            `mask` VARCHAR(32) NOT NULL,
            `api_base` VARCHAR(512) NOT NULL,
            `is_active` TINYINT(1) NOT NULL DEFAULT 1,
            `priority` INT NOT NULL DEFAULT 0,
            `weight` INT NOT NULL DEFAULT 1,
            `remark` VARCHAR(256) NULL,
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_api_channels_slug` (`slug`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `channel_model_abilities` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `channel_id` BIGINT NOT NULL,
            `model_slug` VARCHAR(120) NOT NULL,
            `upstream_model` VARCHAR(200) NOT NULL,
            `is_active` TINYINT(1) NOT NULL DEFAULT 1,
            `priority` INT NOT NULL DEFAULT 0,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            CONSTRAINT `fk_cma_channel` FOREIGN KEY (`channel_id`) REFERENCES `api_channels` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
