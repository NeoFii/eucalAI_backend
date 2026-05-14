"""Table design fixes from review audit.

Addresses:
- P0-1: CHECK constraints on users.balance and frozen_amount
- P0-3: api_call_logs.updated_at missing ON UPDATE CURRENT_TIMESTAMP
- P1-5: api_call_logs missing provider_slug index
- P1-6: user_sessions missing expires_at index
- P2-10: api_call_logs.total_tokens comment correction
- P2-11: usage_stats redundant UNIQUE constraint removal
- P2-12: users monetary columns missing DDL COMMENT
"""

from __future__ import annotations

from alembic import op

revision = "20260514_01_table_design_fixes"
down_revision = "20260505_02_drop_api_key_rpm_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P0-1: CHECK constraints as last-resort guard against negative balance
    op.execute(
        "ALTER TABLE `users` "
        "ADD CONSTRAINT `chk_balance_non_negative` CHECK (`balance` >= 0)"
    )
    op.execute(
        "ALTER TABLE `users` "
        "ADD CONSTRAINT `chk_frozen_non_negative` CHECK (`frozen_amount` >= 0)"
    )

    # P0-3: api_call_logs.updated_at auto-update on modification
    op.execute(
        "ALTER TABLE `api_call_logs` "
        "MODIFY COLUMN `updated_at` datetime NOT NULL "
        "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP "
        "COMMENT 'Updated at'"
    )

    # P1-5: provider_slug index for fault investigation queries
    op.create_index(
        "idx_api_call_logs_provider_created",
        "api_call_logs",
        ["provider_slug", "created_at"],
    )

    # P1-6: expires_at index for session cleanup queries
    op.create_index(
        "idx_user_sessions_expires_at",
        "user_sessions",
        ["expires_at"],
    )

    # P2-10: total_tokens comment correction
    op.execute(
        "ALTER TABLE `api_call_logs` "
        "MODIFY COLUMN `total_tokens` int NOT NULL DEFAULT 0 "
        "COMMENT 'prompt_tokens + completion_tokens (cached_tokens is a subset of prompt, not additive)'"
    )

    # P2-11: remove redundant UNIQUE that doesn't enforce anything due to NULL
    op.drop_index("uk_usage_stats_bucket", table_name="usage_stats")

    # P2-12: users monetary columns missing COMMENT
    op.execute(
        "ALTER TABLE `users` "
        "MODIFY COLUMN `balance` bigint NOT NULL DEFAULT 0 "
        "COMMENT '可用余额（微元，¥1=1000000）', "
        "MODIFY COLUMN `frozen_amount` bigint NOT NULL DEFAULT 0 "
        "COMMENT '预冻结中的余额（微元）', "
        "MODIFY COLUMN `used_amount` bigint NOT NULL DEFAULT 0 "
        "COMMENT '历史累计消费（微元）'"
    )


def downgrade() -> None:
    # P2-12: revert comments (columns stay, just lose comments)
    op.execute(
        "ALTER TABLE `users` "
        "MODIFY COLUMN `balance` bigint NOT NULL DEFAULT 0, "
        "MODIFY COLUMN `frozen_amount` bigint NOT NULL DEFAULT 0, "
        "MODIFY COLUMN `used_amount` bigint NOT NULL DEFAULT 0"
    )

    # P2-11: restore redundant UNIQUE
    op.create_unique_constraint(
        "uk_usage_stats_bucket",
        "usage_stats",
        ["user_id", "api_key_id", "model_name", "stat_hour"],
    )

    # P2-10: revert total_tokens comment
    op.execute(
        "ALTER TABLE `api_call_logs` "
        "MODIFY COLUMN `total_tokens` int NOT NULL DEFAULT 0 "
        "COMMENT 'prompt+completion+cached'"
    )

    # P1-6
    op.drop_index("idx_user_sessions_expires_at", table_name="user_sessions")

    # P1-5
    op.drop_index("idx_api_call_logs_provider_created", table_name="api_call_logs")

    # P0-3: revert updated_at (remove ON UPDATE)
    op.execute(
        "ALTER TABLE `api_call_logs` "
        "MODIFY COLUMN `updated_at` datetime NOT NULL "
        "DEFAULT CURRENT_TIMESTAMP "
        "COMMENT 'Updated at'"
    )

    # P0-1
    op.execute("ALTER TABLE `users` DROP CONSTRAINT `chk_balance_non_negative`")
    op.execute("ALTER TABLE `users` DROP CONSTRAINT `chk_frozen_non_negative`")
