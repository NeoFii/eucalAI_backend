"""Alembic revision helpers for runtime startup checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.ext.asyncio.engine import AsyncConnection


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ServiceMigrationConfig:
    service: str
    package: str
    script_location: Path
    alembic_ini_path: Path
    database_env: str


SERVICE_CONFIGS = {
    "admin-service": ServiceMigrationConfig(
        service="admin-service",
        package="admin_service",
        script_location=(ROOT / "migrations" / "admin_service").resolve(),
        alembic_ini_path=(ROOT / "migrations" / "admin_service" / "alembic.ini").resolve(),
        database_env="ADMIN_DATABASE_URL",
    ),
    "user-service": ServiceMigrationConfig(
        service="user-service",
        package="user_service",
        script_location=(ROOT / "migrations" / "user_service").resolve(),
        alembic_ini_path=(ROOT / "migrations" / "user_service" / "alembic.ini").resolve(),
        database_env="USER_DATABASE_URL",
    ),
}


def build_service_alembic_config(service_name: str, url: str | None = None) -> Config:
    service = SERVICE_CONFIGS[service_name]
    config = Config(str(service.alembic_ini_path))
    if url:
        config.set_main_option("sqlalchemy.url", _escape_config_value(url))
    return config


def _escape_config_value(value: str) -> str:
    """Escape values written through ConfigParser-backed Alembic options."""

    return value.replace("%", "%%")


def get_head_revision(service_name: str) -> str:
    config = build_service_alembic_config(service_name)
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


async def get_current_revision(*, service_name: str, url: str) -> str | None:
    config = build_service_alembic_config(service_name, url)
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def _read_revision(connection: AsyncConnection) -> str | None:
        def _sync(sync_connection):
            context = MigrationContext.configure(sync_connection)
            return context.get_current_revision()

        return await connection.run_sync(_sync)

    try:
        async with connectable.connect() as connection:
            return await _read_revision(connection)
    finally:
        await connectable.dispose()


async def ensure_database_at_head(*, service_name: str, url: str) -> None:
    current = await get_current_revision(service_name=service_name, url=url)
    head = get_head_revision(service_name)
    if current == head:
        return
    raise RuntimeError(
        f"{service_name} database is at {current!r}, expected {head!r}; "
        f"run: uv run migrate --service {service_name} upgrade head"
    )
