"""Add route monitor columns to api_call_logs.

Adds 6 new columns to support the route monitoring panel:
- total_score_0_10:    routing total score (0-10) from inference-service
- upstream_latency_ms: upstream LLM call latency (separate from total duration)
- messages_count:      message count in the request
- routing_detail:      JSON blob (scores_0_2, proto_weighted_0_2, fallback_routes,
                       tier_model_map, score_bands_raw); admin-visible
- request_preview:     JSON blob (input messages + response_text); super_admin only
- input_hash:          sha256(canonical(messages))[:32] for replay/compare view

And 2 indexes:
- idx_api_call_logs_tier_created       (routing_tier, created_at)   tier histograms
- idx_api_call_logs_input_hash_created (input_hash, created_at)     compare view
"""

from __future__ import annotations

from alembic import op

revision = "20260504_01_add_route_monitor_columns"
down_revision = "20260430_02_monetary_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE `api_call_logs`
          ADD COLUMN `total_score_0_10`    DECIMAL(6,4) NULL
              COMMENT '路由总分 0-10'
              AFTER `score_source`,
          ADD COLUMN `upstream_latency_ms` INT NULL
              COMMENT '上游 LLM 调用耗时(ms)'
              AFTER `duration_ms`,
          ADD COLUMN `messages_count`      SMALLINT NULL
              COMMENT '请求消息条数'
              AFTER `is_stream`,
          ADD COLUMN `routing_detail`      JSON NULL
              COMMENT '评分明细 scores_0_2/proto_weighted/fallback_routes/tier_model_map/score_bands_raw',
          ADD COLUMN `request_preview`     JSON NULL
              COMMENT '请求/响应原文(super_admin only) messages/response_text/is_truncated',
          ADD COLUMN `input_hash`          VARCHAR(32) NULL
              COMMENT 'sha256(canonical(messages)) first 32 hex chars，用于对比回放',
          ADD KEY `idx_api_call_logs_tier_created`        (`routing_tier`, `created_at`),
          ADD KEY `idx_api_call_logs_input_hash_created`  (`input_hash`, `created_at`)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE `api_call_logs`
          DROP KEY `idx_api_call_logs_input_hash_created`,
          DROP KEY `idx_api_call_logs_tier_created`,
          DROP COLUMN `input_hash`,
          DROP COLUMN `request_preview`,
          DROP COLUMN `routing_detail`,
          DROP COLUMN `messages_count`,
          DROP COLUMN `upstream_latency_ms`,
          DROP COLUMN `total_score_0_10`
        """
    )
