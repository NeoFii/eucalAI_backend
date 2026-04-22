"""Replace user vouchers with voucher redemption codes."""

from __future__ import annotations

from alembic import op

revision = "20260422_02_replace_vouchers_with_redemption_codes"
down_revision = "20260422_01_create_user_vouchers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `voucher_transactions`")
    op.execute("DROP TABLE IF EXISTS `user_vouchers`")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `voucher_redemption_codes` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `code_hash` VARCHAR(64) NOT NULL COMMENT 'SHA-256 hash of normalized code',
            `code_prefix` VARCHAR(8) NOT NULL COMMENT 'Non-secret display prefix',
            `code_suffix` VARCHAR(8) NOT NULL COMMENT 'Non-secret display suffix',
            `amount` INT NOT NULL COMMENT 'Redeem amount (fen)',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=active 2=redeemed 3=disabled',
            `starts_at` DATETIME NOT NULL COMMENT 'Code validity start',
            `expires_at` DATETIME NOT NULL COMMENT 'Code validity end',
            `redeemed_user_id` BIGINT NULL COMMENT 'Redeeming users.id',
            `redeemed_at` DATETIME NULL COMMENT 'Redeemed at',
            `created_by_admin_uid` BIGINT NULL COMMENT 'Creator admin uid',
            `remark` VARCHAR(255) NULL COMMENT 'Admin note',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_voucher_codes_code_hash` (`code_hash`),
            KEY `idx_voucher_codes_status` (`status`),
            KEY `idx_voucher_codes_starts_at` (`starts_at`),
            KEY `idx_voucher_codes_expires_at` (`expires_at`),
            KEY `idx_voucher_codes_redeemed_user` (`redeemed_user_id`),
            KEY `idx_voucher_codes_admin_uid` (`created_by_admin_uid`),
            CONSTRAINT `fk_voucher_codes_redeemed_user_id` FOREIGN KEY (`redeemed_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Voucher redemption codes'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `voucher_redemption_codes`")
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
