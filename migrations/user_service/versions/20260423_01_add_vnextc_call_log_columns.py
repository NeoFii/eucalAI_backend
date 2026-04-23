"""VNext-C: add routing trace columns + status enum expansion to api_call_logs."""

from __future__ import annotations

from alembic import op

revision = "20260423_01_add_vnextc_call_log_columns"
down_revision = "20260422_02_replace_vouchers_with_redemption_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE `api_call_logs`
          ADD COLUMN `selected_model` VARCHAR(64) NULL COMMENT 'Routed model name' AFTER `model_name`,
          ADD COLUMN `provider_slug` VARCHAR(32) NULL COMMENT 'Provider identifier' AFTER `selected_model`,
          ADD COLUMN `upstream_model` VARCHAR(64) NULL COMMENT 'Upstream provider model name' AFTER `provider_slug`,
          ADD COLUMN `config_version` INT NULL COMMENT 'Router config version' AFTER `upstream_model`,
          ADD COLUMN `config_source` VARCHAR(32) NULL COMMENT 'Config source' AFTER `config_version`,
          ADD COLUMN `inference_config_version` INT NULL COMMENT 'Inference config version' AFTER `config_source`,
          ADD COLUMN `inference_config_source` VARCHAR(32) NULL COMMENT 'Inference config source' AFTER `inference_config_version`,
          ADD COLUMN `routing_tier` TINYINT NULL COMMENT 'Routing tier 1-5' AFTER `inference_config_source`,
          ADD COLUMN `score_source` VARCHAR(32) NULL COMMENT 'Score source' AFTER `routing_tier`,
          ADD COLUMN `router_trace_id` VARCHAR(64) NULL COMMENT 'Router trace ID' AFTER `score_source`,
          ADD COLUMN `inference_error_code` VARCHAR(32) NULL COMMENT 'Inference service error code' AFTER `router_trace_id`,
          ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Updated at' AFTER `created_at`
        """
    )
    op.execute(
        "ALTER TABLE `api_call_logs` ALTER COLUMN `status` SET DEFAULT 0"
    )
    op.execute(
        """
        ALTER TABLE `api_call_logs`
          MODIFY COLUMN `status` TINYINT NOT NULL DEFAULT 0
            COMMENT '0=pending 1=success 2=error 3=refunded 4=aborted'
        """
    )


def downgrade() -> None:
    op.execute(
        """
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
          DROP COLUMN `router_trace_id`,
          DROP COLUMN `inference_error_code`,
          DROP COLUMN `updated_at`
        """
    )
    op.execute(
        """
        ALTER TABLE `api_call_logs`
          MODIFY COLUMN `status` TINYINT NOT NULL DEFAULT 1
            COMMENT '1=success 2=error 3=refunded'
        """
    )
