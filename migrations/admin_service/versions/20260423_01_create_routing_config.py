"""Create routing_configs and provider_credentials tables."""

from __future__ import annotations

from alembic import op
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    text,
)

revision = "20260423_01_create_routing_config"
down_revision = "20260422_02_add_model_summary_and_fen_pricing"
branch_labels = None
depends_on = None


def _tables() -> list[Table]:
    metadata = MetaData()
    routing_configs = Table(
        "routing_configs",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("version", Integer, nullable=False, unique=True),
        Column("status", String(16), nullable=False, server_default=text("'draft'")),
        Column("config_data", JSON, nullable=False),
        Column("description", String(512), nullable=True),
        Column("published_at", DateTime, nullable=True),
        Column(
            "published_by",
            BigInteger,
            ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        Column(
            "created_by",
            BigInteger,
            ForeignKey("admin_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Index("idx_routing_configs_status", "status"),
    )
    provider_credentials = Table(
        "provider_credentials",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("slug", String(64), nullable=False, unique=True),
        Column("provider_slug", String(64), nullable=False),
        Column("api_key_enc", JSON, nullable=False),
        Column("mask", String(32), nullable=False),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("remark", String(256), nullable=True),
        Column(
            "created_by",
            BigInteger,
            ForeignKey("admin_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    return [provider_credentials, routing_configs]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _tables():
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_tables()):
        table.drop(bind=bind, checkfirst=True)
