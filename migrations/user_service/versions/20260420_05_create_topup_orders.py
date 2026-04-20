"""Create topup_orders.

Tracks one-shot top-up events. payment_channel is `manual` for admin manual
top-ups; alipay/wechat/stripe slots are reserved. payment_raw stores the
raw callback payload for reconciliation. See refactor/user-service.md §3.4.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_05_create_topup_orders"
down_revision = "20260420_04_create_balance_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `topup_orders` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `order_no` VARCHAR(64) NOT NULL COMMENT 'Business order no, TP{yyyyMMdd}{8rand}',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `amount` INT NOT NULL COMMENT 'Top-up amount (分)',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=pending 2=paid 3=cancelled 4=refunded',
            `payment_channel` VARCHAR(32) NOT NULL DEFAULT 'manual'
                COMMENT 'manual / alipay / wechat / stripe',
            `payment_no` VARCHAR(128) NULL COMMENT 'Third-party payment serial',
            `payment_raw` JSON NULL COMMENT 'Third-party callback raw payload',
            `paid_at` DATETIME NULL COMMENT 'Paid timestamp',
            `remark` VARCHAR(255) NULL COMMENT 'Admin note',
            `operator_id` BIGINT NULL COMMENT 'Admin uid for manual top-ups',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_topup_orders_order_no` (`order_no`),
            KEY `idx_topup_orders_user_created` (`user_id`, `created_at`),
            KEY `idx_topup_orders_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Top-up orders'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `topup_orders`")
