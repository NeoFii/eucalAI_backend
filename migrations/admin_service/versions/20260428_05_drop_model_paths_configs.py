"""Drop model_paths_configs table — config now loaded from static file."""

from __future__ import annotations

from alembic import op

revision = "20260428_05_drop_model_paths"
down_revision = "20260428_04_drop_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `model_paths_configs`")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `model_paths_configs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT,
            `version` INT NOT NULL,
            `status` VARCHAR(20) NOT NULL DEFAULT 'draft',
            `description` VARCHAR(512) NULL,
            `config_data` JSON NOT NULL,
            `published_at` DATETIME NULL,
            `created_by` BIGINT NOT NULL,
            `updated_by` BIGINT NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_model_paths_configs_version` (`version`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
