"""Allow multiple ledger rows per usage event."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260313_04_router_ledger"
down_revision = "20260313_03_router_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = {
        item["name"]
        for item in inspector.get_unique_constraints("router_billing_ledger")
    }
    indexes = {
        item["name"]
        for item in inspector.get_indexes("router_billing_ledger")
    }

    if "uk_router_billing_ledger_usage_event" in unique_constraints:
        op.drop_constraint(
            "uk_router_billing_ledger_usage_event",
            "router_billing_ledger",
            type_="unique",
        )
    if "idx_router_billing_ledger_usage_event" not in indexes:
        op.create_index(
            "idx_router_billing_ledger_usage_event",
            "router_billing_ledger",
            ["usage_event_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = {
        item["name"]
        for item in inspector.get_unique_constraints("router_billing_ledger")
    }
    indexes = {
        item["name"]
        for item in inspector.get_indexes("router_billing_ledger")
    }

    if "idx_router_billing_ledger_usage_event" in indexes:
        op.drop_index(
            "idx_router_billing_ledger_usage_event",
            table_name="router_billing_ledger",
        )
    if "uk_router_billing_ledger_usage_event" not in unique_constraints:
        op.create_unique_constraint(
            "uk_router_billing_ledger_usage_event",
            "router_billing_ledger",
            ["usage_event_id"],
        )
