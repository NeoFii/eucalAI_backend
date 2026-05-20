"""Alembic _env_shared.py compatibility proxy — exposes Base for metadata discovery."""

from app.core.db import Base

__all__ = ["Base"]
