"""Create balance_transactions.

Immutable ledger for every balance mutation. `type` encodes
TOPUP/CONSUME/REFUND/FREEZE/UNFREEZE/ADMIN_ADJUST. balance_before and
balance_after snapshot the wallet so the full timeline can be replayed.
See refactor/user-service.md §3.3.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_04_create_balance_transactions"
down_revision = "20260420_03_create_user_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `balance_transactions` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `type` TINYINT NOT NULL COMMENT '1=TOPUP 2=CONSUME 3=REFUND 4=FREEZE 5=UNFREEZE 6=ADMIN_ADJUST',
            `amount` INT NOT NULL COMMENT 'Positive=increase, negative=decrease (分)',
            `balance_before` INT NOT NULL COMMENT 'balance snapshot before change (分)',
            `balance_after` INT NOT NULL COMMENT 'balance snapshot after change (分)',
            `ref_type` VARCHAR(32) NULL COMMENT 'topup_order / api_call',
            `ref_id` VARCHAR(64) NULL COMMENT 'related document id',
            `remark` VARCHAR(255) NULL COMMENT 'admin/system note',
            `operator_id` BIGINT NULL COMMENT 'admin uid when type=ADMIN_ADJUST',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            PRIMARY KEY (`id`),
            KEY `idx_balance_tx_user_created` (`user_id`, `created_at`),
            KEY `idx_balance_tx_type_created` (`type`, `created_at`),
            KEY `idx_balance_tx_ref` (`ref_type`, `ref_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Balance ledger (immutable append-only)'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `balance_transactions`")
