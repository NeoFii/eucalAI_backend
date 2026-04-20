"""Add soft-delete column to user_api_keys."""

from __future__ import annotations

from alembic import op

revision = "20260420_11_add_deleted_at_to_user_api_keys"
down_revision = "20260420_10_billing_idempotency_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE `user_api_keys`
        ADD COLUMN IF NOT EXISTS `deleted_at` DATETIME NULL COMMENT 'Soft delete time'
        AFTER `last_used_at`
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE `user_api_keys`
        DROP COLUMN IF EXISTS `deleted_at`
        """
    )
