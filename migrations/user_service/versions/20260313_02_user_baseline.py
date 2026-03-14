"""User service baseline schema."""

from __future__ import annotations

from alembic import op

from migrations.helpers import create_metadata_objects, drop_metadata_objects
from user_service import models as user_models  # noqa: F401
from user_service.db import Base

revision = "20260313_02_user_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_metadata_objects(op.get_bind(), Base.metadata)


def downgrade() -> None:
    drop_metadata_objects(op.get_bind(), Base.metadata)
