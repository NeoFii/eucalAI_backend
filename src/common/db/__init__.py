"""Platform-level DB primitives for service-local runtimes."""

from common.db.base import SnowflakeIdMixin, SoftDeleteMixin, TimestampMixin
from common.db.query import ListParams, PaginatedResult
from common.db.repository import BaseRepository
from common.db.runtime import ServiceDatabaseRuntime
from common.db.schema_version import (
    SERVICE_CONFIGS,
    ServiceMigrationConfig,
    build_service_alembic_config,
    ensure_database_at_head,
    get_current_revision,
    get_head_revision,
)

__all__ = [
    "BaseRepository",
    "ListParams",
    "PaginatedResult",
    "ServiceDatabaseRuntime",
    "SERVICE_CONFIGS",
    "SnowflakeIdMixin",
    "SoftDeleteMixin",
    "ServiceMigrationConfig",
    "TimestampMixin",
    "build_service_alembic_config",
    "ensure_database_at_head",
    "get_current_revision",
    "get_head_revision",
]
