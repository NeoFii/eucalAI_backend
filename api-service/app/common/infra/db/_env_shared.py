"""Shared Alembic environment logic for all service-local migrations.

Each service's ``migrations/<service>/env.py`` is a thin proxy that calls
``run_env()`` below. The service identity is passed through Alembic's main
options by ``alembic.ini``:

    - ``service_name``     : e.g. "admin-service"
    - ``service_package``  : e.g. "admin_service"
    - ``database_env``     : e.g. "ADMIN_DATABASE_URL"

The shared runner dynamically imports ``<service_package>.db.Base`` and
``<service_package>.models`` so that ``target_metadata`` reflects the
service's ORM, then runs migrations against ``sqlalchemy.url`` (preferred)
or the ``database_env`` environment variable as fallback.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import inspect, pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config


def _require_option(name: str) -> str:
    value = context.config.get_main_option(name)
    if not value:
        raise RuntimeError(
            f"Alembic main option '{name}' must be set; invoke via scripts.migrate CLI."
        )
    return value


def _resolve_url(database_env: str) -> str:
    url = (context.config.get_main_option("sqlalchemy.url") or "").strip()
    if url:
        return url
    env_url = os.getenv(database_env, "").strip()
    if env_url:
        return env_url
    raise RuntimeError(
        f"Database URL for migrations not configured; set {database_env} or pass --url."
    )


def _load_metadata(service_package: str):
    if service_package:
        db_module = importlib.import_module(f"{service_package}.db")
        importlib.import_module(f"{service_package}.models")
    else:
        db_module = importlib.import_module("core.db")
        importlib.import_module("models")
    return db_module.Base.metadata


def _ensure_version_table_capacity(connection) -> None:
    """Allow descriptive revision IDs longer than Alembic's default VARCHAR(32)."""
    inspector = inspect(connection)
    if "alembic_version" not in inspector.get_table_names():
        return
    if connection.dialect.name not in {"mysql", "mariadb"}:
        return
    connection.execute(
        text("ALTER TABLE `alembic_version` MODIFY `version_num` VARCHAR(255) NOT NULL")
    )


def run_env() -> None:
    """Entry point invoked by each service-local env.py proxy."""
    from dotenv import load_dotenv

    load_dotenv()

    config = context.config

    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    service_package = config.get_main_option("service_package") or ""
    database_env = _require_option("database_env")
    target_metadata = _load_metadata(service_package)
    url = _resolve_url(database_env)

    def do_run_migrations(connection) -> None:
        _ensure_version_table_capacity(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    async def run_online() -> None:
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = url
        connectable = async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
            await connection.commit()
        await connectable.dispose()

    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        asyncio.run(run_online())
