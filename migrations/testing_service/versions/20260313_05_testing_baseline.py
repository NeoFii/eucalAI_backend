"""Testing service baseline schema."""

from __future__ import annotations

from alembic import op

from migrations.helpers import (
    create_metadata_objects,
    create_or_replace_view,
    drop_metadata_objects,
    drop_view,
)
from testing_service import models as testing_models  # noqa: F401
from testing_service.db import Base

revision = "20260313_05_testing_baseline"
down_revision = None
branch_labels = None
depends_on = None

PROVIDER_METRICS_RANKED_SQL = """
SELECT
    m.`offering_id`,
    m.`probe_region`,
    m.`throughput_tps`,
    m.`ttft_ms`,
    m.`e2e_latency_ms`,
    m.`measured_at`,
    ROW_NUMBER() OVER (
        PARTITION BY m.`offering_id`, m.`probe_region`
        ORDER BY m.`measured_at` DESC
    ) AS `rn`
FROM `provider_performance_metrics` m
JOIN `model_provider_offerings` o
  ON o.`id` = m.`offering_id`
WHERE m.`success` = 1
  AND o.`is_active` = 1
  AND o.`deleted_at` IS NULL
"""


def upgrade() -> None:
    create_metadata_objects(op.get_bind(), Base.metadata)
    create_or_replace_view(op.get_bind(), "provider_metrics_ranked", PROVIDER_METRICS_RANKED_SQL)


def downgrade() -> None:
    drop_view(op.get_bind(), "provider_metrics_ranked")
    drop_metadata_objects(op.get_bind(), Base.metadata)
