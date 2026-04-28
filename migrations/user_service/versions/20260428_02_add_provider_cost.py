"""Add provider_cost column to api_call_logs."""

from __future__ import annotations

from alembic import op

revision = "20260428_02_add_provider_cost"
down_revision = "20260427_01_operator_id_to_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `api_call_logs` "
        "ADD COLUMN `provider_cost` INT NOT NULL DEFAULT 0 "
        "COMMENT 'Provider-side cost (分)' "
        "AFTER `cost`"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `api_call_logs` DROP COLUMN `provider_cost`")
