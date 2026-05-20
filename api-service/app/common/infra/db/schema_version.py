"""Alembic revision helpers for runtime startup checks."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.ext.asyncio.engine import AsyncConnection


@dataclass(frozen=True)
class ServiceMigrationConfig:
    service: str
    package: str
    script_location: Path
    alembic_ini_path: Path
    database_env: str


def _locate_service_migrations(package: str) -> Path:
    """Locate the migrations directory next to the installed service package."""
    mod = importlib.import_module(package)
    pkg_dir = Path(mod.__file__).resolve().parent
    migrations_dir = pkg_dir.parent.parent / "migrations"
    if not migrations_dir.is_dir():
        raise FileNotFoundError(
            f"Cannot find migrations directory for {package} at {migrations_dir}"
        )
    return migrations_dir


def _build_service_configs() -> dict[str, ServiceMigrationConfig]:
    configs: dict[str, ServiceMigrationConfig] = {}
    for service_name, package, db_env in [
        ("api-service", "app", "DATABASE_URL"),
    ]:
        try:
            mig_dir = _locate_service_migrations(package)
        except (ImportError, FileNotFoundError):
            continue
        configs[service_name] = ServiceMigrationConfig(
            service=service_name,
            package=package,
            script_location=mig_dir,
            alembic_ini_path=mig_dir / "alembic.ini",
            database_env=db_env,
        )
    return configs


SERVICE_CONFIGS = _build_service_configs()


def build_service_alembic_config(service_name: str, url: str | None = None) -> Config:
    service = SERVICE_CONFIGS[service_name]
    config = Config(str(service.alembic_ini_path))
    if url:
        config.set_main_option("sqlalchemy.url", _escape_config_value(url))
    return config


def _escape_config_value(value: str) -> str:
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
        f"run: alembic -c migrations/alembic.ini upgrade head"
    )
