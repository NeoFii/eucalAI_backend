"""Alembic _env_shared.py compatibility proxy — exposes Base for metadata discovery."""

from api_service.core.db import Base

__all__ = ["Base"]
