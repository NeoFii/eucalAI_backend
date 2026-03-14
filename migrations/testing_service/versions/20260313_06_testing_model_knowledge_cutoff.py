"""Add knowledge_cutoff to testing models."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260313_06_testing_kc"
down_revision = "20260313_05_testing_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("models")}

    if "knowledge_cutoff" not in columns:
        op.add_column(
            "models",
            sa.Column("knowledge_cutoff", sa.Date(), nullable=True, comment="Knowledge cutoff date"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("models")}

    if "knowledge_cutoff" in columns:
        op.drop_column("models", "knowledge_cutoff")
