"""Drop invitation_codes table and purge invitation audit records."""

from alembic import op

revision = "20260423_02_drop_invitation_codes"
down_revision = "20260423_01_admin_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM `admin_audit_logs` WHERE `action` IN "
        "('generate_invitation_codes', 'enable_invitation_code', "
        "'disable_invitation_code', 'update_invitation_code')"
    )
    op.execute("DROP TABLE IF EXISTS `invitation_codes`")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `invitation_codes` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `code` VARCHAR(64) NOT NULL COMMENT 'Invitation code',
            `status` SMALLINT NOT NULL DEFAULT 0 COMMENT '0=unused 1=used 2=disabled',
            `created_by` BIGINT NULL COMMENT 'Creator admin id',
            `used_by` BIGINT NULL COMMENT 'Used-by user UID',
            `used_at` DATETIME NULL COMMENT 'Used at',
            `expires_at` DATETIME NULL COMMENT 'Expires at',
            `remark` TEXT NULL COMMENT 'Remark',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_invitation_codes_code` (`code`),
            KEY `idx_invitation_codes_created_by` (`created_by`),
            KEY `idx_invitation_codes_used_by` (`used_by`),
            CONSTRAINT `fk_invitation_codes_created_by`
                FOREIGN KEY (`created_by`) REFERENCES `admin_users` (`id`)
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Invitation codes'
        """
    )
