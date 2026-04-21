"""Lifecycle orchestration for the combined backend app."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from admin_service import db as admin_db
from admin_service.config import settings as admin_settings
from admin_service.models import SERVICE_MODELS as ADMIN_MODELS
from admin_service.services.bootstrap_service import AdminBootstrapService
from backend_app.config import settings
from common.observability import log_event
from common.utils.snowflake import configure_snowflake
from testing_service import db as testing_db
from testing_service.config import get_settings as get_testing_settings
from testing_service.models import SERVICE_MODELS as TESTING_MODELS
from user_service import db as user_db
from user_service.config import settings as user_settings
from user_service.models import SERVICE_MODELS as USER_MODELS

testing_settings = get_testing_settings()

LifecycleCallback = Callable[[], Awaitable[None] | None]


@dataclass(slots=True)
class LifecycleRegistration:
    """Pair startup and shutdown callbacks under a stable name."""

    name: str
    startup: LifecycleCallback | None = None
    shutdown: LifecycleCallback | None = None


async def _run_callback(callback: LifecycleCallback | None) -> None:
    if callback is None:
        return
    result = callback()
    if inspect.isawaitable(result):
        await result


class LifecycleManager:
    """Execute startup in registration order and shutdown in reverse order."""

    def __init__(self) -> None:
        self._registrations: list[LifecycleRegistration] = []
        self._started: list[LifecycleRegistration] = []

    def register(
        self,
        name: str,
        *,
        startup: LifecycleCallback | None = None,
        shutdown: LifecycleCallback | None = None,
    ) -> None:
        self._registrations.append(
            LifecycleRegistration(name=name, startup=startup, shutdown=shutdown)
        )

    async def startup(self) -> None:
        self._started = []
        try:
            for registration in self._registrations:
                await _run_callback(registration.startup)
                self._started.append(registration)
        except Exception as exc:
            try:
                await self._shutdown_registrations(self._started)
            except Exception:  # pragma: no cover - preserve startup failure context
                pass
            raise exc

    async def shutdown(self) -> None:
        await self._shutdown_registrations(self._started)

    async def _shutdown_registrations(
        self,
        registrations: list[LifecycleRegistration],
    ) -> None:
        errors: list[BaseException] = []
        for registration in reversed(registrations):
            try:
                await _run_callback(registration.shutdown)
            except Exception as exc:  # pragma: no cover - shutdown failure fan-in
                errors.append(exc)
        self._started = []
        if errors:
            raise errors[0]

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        app.state.lifecycle_manager = self
        await self.startup()
        try:
            yield
        finally:
            await self.shutdown()


async def _initialize_database(
    *,
    service_name: str,
    create_engine: Callable[..., Any],
    init_session_factory: Callable[[], Any],
    init_db: Callable[[list[type]], Awaitable[None]],
    database_url: str,
    pool_size: int,
    max_overflow: int,
    echo: bool,
    auto_init: bool,
    models: list[type],
    logger: logging.Logger,
) -> None:
    create_engine(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )
    init_session_factory()
    if auto_init:
        await init_db(models)
        log_event(logger, logging.INFO, "schema_auto_init_enabled", service=service_name)
    else:
        log_event(logger, logging.INFO, "schema_auto_init_skipped", service=service_name)


def build_lifecycle_manager(*, logger: logging.Logger) -> LifecycleManager:
    """Build the backend-app lifecycle with a single orchestration path."""

    manager = LifecycleManager()

    manager.register(
        "service-starting-log",
        startup=lambda: log_event(
            logger,
            logging.INFO,
            "service_starting",
            service=settings.SERVICE_NAME,
        ),
    )
    manager.register(
        "snowflake",
        startup=lambda: configure_snowflake(
            worker_id=settings.SNOWFLAKE_WORKER_ID,
            datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
        ),
    )
    manager.register(
        "admin-database",
        startup=lambda: _initialize_database(
            service_name=admin_settings.SERVICE_NAME,
            create_engine=admin_db.create_engine,
            init_session_factory=admin_db.init_session_factory,
            init_db=admin_db.init_db,
            database_url=admin_settings.DATABASE_URL,
            pool_size=admin_settings.DATABASE_POOL_SIZE,
            max_overflow=admin_settings.DATABASE_MAX_OVERFLOW,
            echo=admin_settings.DATABASE_ECHO,
            auto_init=admin_settings.AUTO_INIT_DB,
            models=list(ADMIN_MODELS),
            logger=logger,
        ),
        shutdown=admin_db.close_db,
    )
    manager.register(
        "user-database",
        startup=lambda: _initialize_database(
            service_name=user_settings.SERVICE_NAME,
            create_engine=user_db.create_engine,
            init_session_factory=user_db.init_session_factory,
            init_db=user_db.init_db,
            database_url=user_settings.DATABASE_URL,
            pool_size=user_settings.DATABASE_POOL_SIZE,
            max_overflow=user_settings.DATABASE_MAX_OVERFLOW,
            echo=user_settings.DATABASE_ECHO,
            auto_init=user_settings.AUTO_INIT_DB,
            models=list(USER_MODELS),
            logger=logger,
        ),
        shutdown=user_db.close_db,
    )
    manager.register(
        "testing-database",
        startup=lambda: _initialize_database(
            service_name=testing_settings.SERVICE_NAME,
            create_engine=testing_db.create_engine,
            init_session_factory=testing_db.init_session_factory,
            init_db=testing_db.init_db,
            database_url=testing_settings.DATABASE_URL,
            pool_size=testing_settings.DATABASE_POOL_SIZE,
            max_overflow=testing_settings.DATABASE_MAX_OVERFLOW,
            echo=testing_settings.DATABASE_ECHO,
            auto_init=testing_settings.auto_init_db,
            models=list(TESTING_MODELS),
            logger=logger,
        ),
        shutdown=testing_db.close_db,
    )
    manager.register(
        "admin-bootstrap",
        startup=_bootstrap_super_admin(logger),
    )
    manager.register(
        "testing-probe-scheduler-warning",
        startup=_warn_probe_scheduler_flag(logger),
    )
    manager.register(
        "service-started-log",
        startup=lambda: log_event(
            logger,
            logging.INFO,
            "service_started",
            service=settings.SERVICE_NAME,
            port=settings.PORT,
            domains=["admin", "user", "testing"],
        ),
    )
    manager.register(
        "service-stopping-log",
        shutdown=lambda: log_event(
            logger,
            logging.INFO,
            "service_stopping",
            service=settings.SERVICE_NAME,
        ),
    )
    return manager


def _bootstrap_super_admin(logger: logging.Logger) -> LifecycleCallback:
    async def run() -> None:
        bootstrap_created = await AdminBootstrapService.ensure_super_admin()
        log_event(
            logger,
            logging.INFO,
            "super_admin_bootstrap_completed",
            service=settings.SERVICE_NAME,
            created=bootstrap_created,
            enabled=admin_settings.BOOTSTRAP_SUPERADMIN_ENABLED,
            required=admin_settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP,
        )

    return run


def _warn_probe_scheduler_flag(logger: logging.Logger) -> LifecycleCallback:
    def run() -> None:
        if testing_settings.probe_scheduler_enabled:
            log_event(
                logger,
                logging.WARNING,
                "probe_scheduler_flag_ignored_in_backend_app",
                service=settings.SERVICE_NAME,
                note="testing-scheduler must run as a separate process",
            )

    return run
