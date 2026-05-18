"""Database runtime for api-service — single engine, single Base."""

from __future__ import annotations

from api_service.common.infra.db.base import Base
from api_service.common.infra.db.runtime import ServiceDatabaseRuntime

_runtime = ServiceDatabaseRuntime(Base)

create_engine = _runtime.create_engine
get_engine = _runtime.get_engine
init_session_factory = _runtime.init_session_factory
get_db = _runtime.get_db
get_db_context = _runtime.get_db_context
close_db = _runtime.close_db

__all__ = [
    "Base",
    "create_engine",
    "get_engine",
    "init_session_factory",
    "get_db",
    "get_db_context",
    "close_db",
]
