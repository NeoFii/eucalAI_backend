"""Upgrade api_call_logs from 14-column compact schema to full ORM schema.

The baseline migration used a compact design (log_type + quota + other JSON).
The merged api-service ORM model requires explicit columns for routing,
token counting, cost breakdown, and error tracking.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "20260520_upgrade_call_logs"
down_revision = "20260519_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Add new columns ---
    op.execute(text("""
        ALTER TABLE `api_call_logs`
            ADD COLUMN `selected_model` VARCHAR(64) NULL COMMENT 'Routed model name' AFTER `model_name`,
            ADD COLUMN `provider_slug` VARCHAR(32) NULL COMMENT 'Provider identifier' AFTER `selected_model`,
            ADD COLUMN `upstream_model` VARCHAR(64) NULL COMMENT 'Upstream provider model name' AFTER `provider_slug`,
            ADD COLUMN `config_version` INT NULL COMMENT 'Router config version' AFTER `upstream_model`,
            ADD COLUMN `config_source` VARCHAR(32) NULL COMMENT 'Config source (admin/local)' AFTER `config_version`,
            ADD COLUMN `inference_config_version` INT NULL COMMENT 'Inference config version' AFTER `config_source`,
            ADD COLUMN `inference_config_source` VARCHAR(32) NULL COMMENT 'Inference config source' AFTER `inference_config_version`,
            ADD COLUMN `routing_tier` SMALLINT NULL COMMENT 'Routing tier 1-5' AFTER `inference_config_source`,
            ADD COLUMN `score_source` VARCHAR(32) NULL COMMENT 'Score source' AFTER `routing_tier`,
            ADD COLUMN `total_score_0_10` DECIMAL(6,4) NULL COMMENT 'Routing total score 0-10' AFTER `score_source`,
            ADD COLUMN `router_trace_id` VARCHAR(64) NULL COMMENT 'Router trace ID' AFTER `total_score_0_10`,
            ADD COLUMN `inference_error_code` VARCHAR(32) NULL COMMENT 'Inference service error code' AFTER `router_trace_id`,
            ADD COLUMN `cached_tokens` INT NOT NULL DEFAULT 0 COMMENT 'Cache-hit tokens' AFTER `completion_tokens`,
            ADD COLUMN `total_tokens` INT NOT NULL DEFAULT 0 COMMENT 'prompt+completion+cached' AFTER `cached_tokens`,
            ADD COLUMN `cost` BIGINT NOT NULL DEFAULT 0 COMMENT 'User-side total charge (micro-yuan)' AFTER `total_tokens`,
            ADD COLUMN `provider_cost` BIGINT NOT NULL DEFAULT 0 COMMENT 'Provider-side cost (micro-yuan)' AFTER `cost`,
            ADD COLUMN `cost_detail` JSON NULL COMMENT 'Admin-only unit price breakdown' AFTER `provider_cost`,
            ADD COLUMN `status` SMALLINT NULL COMMENT 'HTTP status code' AFTER `cost_detail`,
            ADD COLUMN `upstream_latency_ms` INT NULL COMMENT 'Upstream LLM call latency (ms)' AFTER `duration_ms`,
            ADD COLUMN `messages_count` SMALLINT NULL COMMENT 'Number of messages in request' AFTER `is_stream`,
            ADD COLUMN `error_code` VARCHAR(32) NULL COMMENT 'Machine-readable error identifier' AFTER `ip`,
            ADD COLUMN `error_msg` VARCHAR(512) NULL COMMENT 'Human-readable error message' AFTER `error_code`,
            ADD COLUMN `routing_detail` JSON NULL COMMENT 'Routing scoring detail (admin-visible)' AFTER `error_msg`,
            ADD COLUMN `request_preview` JSON NULL COMMENT 'Request/response preview (super_admin only)' AFTER `routing_detail`,
            ADD COLUMN `input_hash` VARCHAR(32) NULL COMMENT 'Truncated sha256 hash of canonical messages' AFTER `request_preview`,
            ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at' AFTER `created_at`
    """))

    # --- Backfill total_tokens from existing data ---
    op.execute(text("""
        UPDATE `api_call_logs`
        SET `total_tokens` = `prompt_tokens` + `completion_tokens`
        WHERE `total_tokens` = 0 AND (`prompt_tokens` > 0 OR `completion_tokens` > 0)
    """))

    # --- Backfill cost from legacy quota column ---
    op.execute(text("""
        UPDATE `api_call_logs`
        SET `cost` = `quota`
        WHERE `cost` = 0 AND `quota` > 0
    """))

    # --- Add indexes for new query patterns ---
    op.execute(text("""
        CREATE INDEX `idx_api_call_logs_status` ON `api_call_logs` (`status`)
    """))
    op.execute(text("""
        CREATE INDEX `idx_api_call_logs_provider` ON `api_call_logs` (`provider_slug`, `created_at`)
    """))


def downgrade() -> None:
    op.execute(text("ALTER TABLE `api_call_logs` DROP INDEX `idx_api_call_logs_provider`"))
    op.execute(text("ALTER TABLE `api_call_logs` DROP INDEX `idx_api_call_logs_status`"))
    op.execute(text("""
        ALTER TABLE `api_call_logs`
            DROP COLUMN `selected_model`,
            DROP COLUMN `provider_slug`,
            DROP COLUMN `upstream_model`,
            DROP COLUMN `config_version`,
            DROP COLUMN `config_source`,
            DROP COLUMN `inference_config_version`,
            DROP COLUMN `inference_config_source`,
            DROP COLUMN `routing_tier`,
            DROP COLUMN `score_source`,
            DROP COLUMN `total_score_0_10`,
            DROP COLUMN `router_trace_id`,
            DROP COLUMN `inference_error_code`,
            DROP COLUMN `cached_tokens`,
            DROP COLUMN `total_tokens`,
            DROP COLUMN `cost`,
            DROP COLUMN `provider_cost`,
            DROP COLUMN `cost_detail`,
            DROP COLUMN `status`,
            DROP COLUMN `upstream_latency_ms`,
            DROP COLUMN `messages_count`,
            DROP COLUMN `error_code`,
            DROP COLUMN `error_msg`,
            DROP COLUMN `routing_detail`,
            DROP COLUMN `request_preview`,
            DROP COLUMN `input_hash`,
            DROP COLUMN `updated_at`
    """))
