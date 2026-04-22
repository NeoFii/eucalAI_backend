"""Create user voucher tables."""

from __future__ import annotations

from alembic import op

revision = "20260422_01_create_user_vouchers"
down_revision = "20260420_11_add_deleted_at_to_user_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `user_vouchers` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=disabled',
            `original_amount` INT NOT NULL COMMENT 'Initial voucher amount (fen)',
            `remaining_amount` INT NOT NULL DEFAULT 0 COMMENT 'Unfrozen usable amount (fen)',
            `frozen_amount` INT NOT NULL DEFAULT 0 COMMENT 'Frozen amount (fen)',
            `used_amount` INT NOT NULL DEFAULT 0 COMMENT 'Consumed amount (fen)',
            `expires_at` DATETIME NULL COMMENT 'NULL = never expires',
            `created_by_admin_uid` BIGINT NULL COMMENT 'Creator admin uid',
            `remark` VARCHAR(255) NULL COMMENT 'Admin note',
            `deleted_at` DATETIME NULL COMMENT 'Soft deleted at',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            KEY `idx_user_vouchers_user_id` (`user_id`),
            KEY `idx_user_vouchers_status` (`status`),
            KEY `idx_user_vouchers_expires_at` (`expires_at`),
            KEY `idx_user_vouchers_admin_uid` (`created_by_admin_uid`),
            KEY `idx_user_vouchers_deleted_at` (`deleted_at`),
            CONSTRAINT `fk_user_vouchers_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User vouchers'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `voucher_transactions` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `voucher_id` BIGINT NOT NULL COMMENT 'FK user_vouchers.id',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `type` TINYINT NOT NULL COMMENT '1=ISSUE 2=FREEZE 3=CONSUME 4=RELEASE 5=ADMIN_UPDATE 6=DELETE',
            `amount` INT NOT NULL COMMENT 'Voucher amount delta (fen)',
            `balance_before` INT NOT NULL COMMENT 'Remaining amount before change (fen)',
            `balance_after` INT NOT NULL COMMENT 'Remaining amount after change (fen)',
            `ref_type` VARCHAR(32) NULL COMMENT 'api_call / admin',
            `ref_id` VARCHAR(64) NULL COMMENT 'Related document id',
            `operator_id` BIGINT NULL COMMENT 'Admin uid when applicable',
            `remark` VARCHAR(255) NULL COMMENT 'Admin/system note',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            PRIMARY KEY (`id`),
            KEY `idx_voucher_tx_voucher_id` (`voucher_id`),
            KEY `idx_voucher_tx_user_id` (`user_id`),
            KEY `idx_voucher_tx_ref` (`ref_type`, `ref_id`),
            KEY `idx_voucher_tx_type_created` (`type`, `created_at`),
            CONSTRAINT `fk_voucher_tx_voucher_id` FOREIGN KEY (`voucher_id`) REFERENCES `user_vouchers` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_voucher_tx_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Voucher mutation ledger'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `voucher_transactions`")
    op.execute("DROP TABLE IF EXISTS `user_vouchers`")
