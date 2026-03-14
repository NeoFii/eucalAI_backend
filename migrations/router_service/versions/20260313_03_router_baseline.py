"""Router service baseline schema."""

from __future__ import annotations

from alembic import op

from migrations.helpers import create_metadata_objects, drop_metadata_objects
from router_service import models as router_models  # noqa: F401
from router_service.db import Base

revision = "20260313_03_router_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_metadata_objects(op.get_bind(), Base.metadata)


def downgrade() -> None:
    drop_metadata_objects(op.get_bind(), Base.metadata)
