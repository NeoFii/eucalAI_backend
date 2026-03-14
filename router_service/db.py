"""Router-service database runtime."""

from sqlalchemy.orm import declarative_base

from common.db.runtime import ServiceDatabaseRuntime

Base = declarative_base()
_runtime = ServiceDatabaseRuntime(Base)

create_engine = _runtime.create_engine
get_engine = _runtime.get_engine
init_session_factory = _runtime.init_session_factory
get_db = _runtime.get_db
get_db_context = _runtime.get_db_context
init_db = _runtime.init_db
close_db = _runtime.close_db

__all__ = [
    "Base",
    "close_db",
    "create_engine",
    "get_db",
    "get_db_context",
    "get_engine",
    "init_db",
    "init_session_factory",
]