"""Database runtime for api-service — single engine, single Base."""

from __future__ import annotations

from app.common.infra.db.base import Base
from app.common.infra.db.runtime import ServiceDatabaseRuntime

_runtime = ServiceDatabaseRuntime(Base)

create_engine = _runtime.create_engine
get_engine = _runtime.get_engine
init_session_factory = _runtime.init_session_factory
get_db = _runtime.get_db
get_db_context = _runtime.get_db_context
close_db = _runtime.close_db


def get_session_factory():
    """Return the initialized session factory."""
    if _runtime._session_factory is None:
        raise RuntimeError("Session factory has not been initialized")
    return _runtime._session_factory


__all__ = [
    "Base",
    "create_engine",
    "get_engine",
    "init_session_factory",
    "get_session_factory",
    "get_db",
    "get_db_context",
    "close_db",
]
