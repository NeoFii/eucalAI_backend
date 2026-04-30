"""Add routing_slug to supported_models for pool_models mapping."""

from __future__ import annotations

from alembic import op

revision = "20260429_08_routing_slug"
down_revision = "20260428_07_pool_health_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `supported_models` "
        "ADD COLUMN `routing_slug` VARCHAR(200) NULL "
        "COMMENT '路由用 slug，对应 pool_models.model_slug' "
        "AFTER `slug`"
    )
    op.execute(
        "CREATE UNIQUE INDEX `uk_supported_models_routing_slug` "
        "ON `supported_models` (`routing_slug`)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX `uk_supported_models_routing_slug` ON `supported_models`")
    op.execute("ALTER TABLE `supported_models` DROP COLUMN `routing_slug`")
