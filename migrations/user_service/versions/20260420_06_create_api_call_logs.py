"""Create api_call_logs.

Per-request audit log written by router-service via HMAC. cost_detail is a
JSON envelope with per-unit prices + markup_rate. `cost_detail` is admin-only
in responses; user-facing endpoints strip it. See refactor/user-service.md §3.5.
"""

from __future__ import annotations

from alembic import op

revision = "20260420_06_create_api_call_logs"
down_revision = "20260420_05_create_topup_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS `api_call_logs` (
            `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Internal primary key',
            `request_id` VARCHAR(64) NOT NULL COMMENT 'Global request id, spans 3-phase billing',
            `user_id` BIGINT NOT NULL COMMENT 'FK users.id',
            `api_key_id` BIGINT NULL COMMENT 'FK user_api_keys.id, NULL if key not used',
            `model_name` VARCHAR(64) NOT NULL COMMENT 'Logical model name',
            `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Prompt tokens',
            `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Completion tokens',
            `cached_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens',
            `total_tokens` INT NOT NULL DEFAULT 0 COMMENT 'prompt+completion+cached',
            `cost` INT NOT NULL DEFAULT 0 COMMENT 'User-side total charge (分)',
            `cost_detail` JSON NULL COMMENT 'Admin-only unit price breakdown',
            `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1=success 2=error 3=refunded',
            `duration_ms` INT NULL COMMENT 'Request latency (ms)',
            `is_stream` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '0=non-stream 1=stream',
            `ip` VARCHAR(45) NULL COMMENT 'Caller IP; gated by user record_ip setting',
            `error_code` VARCHAR(32) NULL COMMENT 'status=2 payload',
            `error_msg` VARCHAR(512) NULL COMMENT 'status=2 message',
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_api_call_logs_request_id` (`request_id`),
            KEY `idx_api_call_logs_user_created` (`user_id`, `created_at`),
            KEY `idx_api_call_logs_key_created` (`api_key_id`, `created_at`),
            KEY `idx_api_call_logs_model_created` (`model_name`, `created_at`),
            KEY `idx_api_call_logs_status_created` (`status`, `created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='API call audit log written by router-service'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS `api_call_logs`")
