"""Change operator_id from BIGINT to VARCHAR(20) for NanoID storage."""

from __future__ import annotations

from alembic import op

revision = "20260427_01_operator_id_to_varchar"
down_revision = "20260423_01_user_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `balance_transactions` "
        "MODIFY COLUMN `operator_id` VARCHAR(20) NULL "
        "COMMENT 'admin NanoID uid when type=ADMIN_ADJUST'"
    )
    op.execute(
        "ALTER TABLE `topup_orders` "
        "MODIFY COLUMN `operator_id` VARCHAR(20) NULL "
        "COMMENT 'Admin NanoID uid for manual top-ups'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `balance_transactions` "
        "MODIFY COLUMN `operator_id` BIGINT NULL "
        "COMMENT 'admin uid when type=ADMIN_ADJUST'"
    )
    op.execute(
        "ALTER TABLE `topup_orders` "
        "MODIFY COLUMN `operator_id` BIGINT NULL "
        "COMMENT 'Admin uid for manual top-ups'"
    )
