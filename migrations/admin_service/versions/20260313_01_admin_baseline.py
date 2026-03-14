"""Admin service baseline schema."""

from __future__ import annotations

from alembic import op

from admin_service import models as admin_models  # noqa: F401
from admin_service.db import Base
from migrations.helpers import create_metadata_objects, drop_metadata_objects

revision = "20260313_01_admin_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_metadata_objects(op.get_bind(), Base.metadata)


def downgrade() -> None:
    drop_metadata_objects(op.get_bind(), Base.metadata)
