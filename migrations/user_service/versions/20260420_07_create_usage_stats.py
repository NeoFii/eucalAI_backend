"""Create usage_stats.

Hourly aggregate written by the user-service arq worker. Each api_call_logs
row produces TWO rows here: one keyed on (user, api_key) and one keyed on
(user, NULL) for account-level totals. Idempotency is via the `uk_stat` unique
key + INSERT ... ON DUPLICATE KEY UPDATE. See refactor/user-service.md §3.6.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_07_create_usage_stats"
down_revision = "20260420_06_create_api_call_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `usage_stats` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `api_key_id` BIGINT NULL COMMENT 'NULL = account-wide bucket',
            `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
            `stat_hour` DATETIME NOT NULL COMMENT 'Aligned to the hour (UTC)',
            `request_count` INT NOT NULL DEFAULT 0 COMMENT 'Total calls',
            `success_count` INT NOT NULL DEFAULT 0 COMMENT 'status=1 calls',
            `error_count` INT NOT NULL DEFAULT 0 COMMENT 'status=2 calls',
            `prompt_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens sum',
            `completion_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Completion tokens sum',
            `cached_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens sum',
            `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT 'Total tokens sum',
            `total_cost` INT NOT NULL DEFAULT 0 COMMENT 'Total cost (分)',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_usage_stats_bucket` (`user_id`, `api_key_id`, `model_name`, `stat_hour`),
            KEY `idx_usage_stats_user_hour` (`user_id`, `stat_hour`),
            KEY `idx_usage_stats_key_hour` (`api_key_id`, `stat_hour`),
            KEY `idx_usage_stats_hour` (`stat_hour`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Hourly usage aggregates written by arq worker'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `usage_stats`")
