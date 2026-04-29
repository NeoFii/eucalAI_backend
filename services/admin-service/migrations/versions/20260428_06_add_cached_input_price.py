"""Add price_cached_input_per_m_fen to supported_models."""

from __future__ import annotations

from alembic import op

revision = "20260428_06_add_cached_input_price"
down_revision = "20260428_05_drop_model_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `supported_models` "
        "ADD COLUMN `price_cached_input_per_m_fen` INT NULL "
        "COMMENT 'Cached input price per million tokens in fen' "
        "AFTER `price_output_per_m_fen`"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `supported_models` DROP COLUMN `price_cached_input_per_m_fen`"
    )
