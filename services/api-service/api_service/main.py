"""FastAPI application entry point for the unified api-service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_service.common.core.exception_handlers import register_exception_handlers
from api_service.common.observability import (
    configure_logging_from_settings,
    install_observability,
    log_event,
)
from api_service.common.utils.snowflake import configure_snowflake
from api_service.core.config import settings
from api_service.core.lifespan import LifespanRegistry
from api_service.core.router import api_router

# Configure logging before anything else
configure_logging_from_settings(settings)

logger = logging.getLogger(__name__)

# ── Lifespan Registry ────────────────────────────────────────────────────────

registry = LifespanRegistry()


async def _init_logging() -> None:
    """Formalized logging registration (already configured at module level)."""
    configure_logging_from_settings(settings)


async def _init_snowflake() -> None:
    """Configure snowflake ID generator with process-unique worker_id."""
    configure_snowflake(
        worker_id=os.getpid() % 32,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )


registry.register("logging", init_fn=_init_logging, priority=0)
registry.register("snowflake", init_fn=_init_snowflake, priority=10)


async def _init_database() -> None:
    """Initialize SQLAlchemy async engine and session factory."""
    from api_service.core.db import create_engine, init_session_factory

    create_engine(
        settings.DATABASE_URL,
        echo=settings.DATABASE_ECHO,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    )
    init_session_factory()


async def _shutdown_database() -> None:
    """Dispose DB engine and clear session factory."""
    from api_service.core.db import close_db

    await close_db()


registry.register(
    "database", init_fn=_init_database, shutdown_fn=_shutdown_database, priority=20
)


# ── Lifespan Context Manager ─────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.startup()
    log_event(logger, logging.INFO, "service_started", service=settings.SERVICE_NAME)
    yield
    await registry.shutdown()
    log_event(logger, logging.INFO, "service_stopped", service=settings.SERVICE_NAME)


# ── FastAPI Application ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
    redirect_slashes=False,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_observability(app, service_name=settings.SERVICE_NAME)

# ── Exception Handlers ───────────────────────────────────────────────────────

register_exception_handlers(app)

# ── Routes ───────────────────────────────────────────────────────────────────

app.include_router(api_router)


@app.get("/health")
async def health():
    """Liveness probe — always returns healthy if the process is running."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
    }


@app.get("/ready")
async def ready():
    """Readiness probe — checks database connectivity."""
    from api_service.common.health import build_readiness_response, check_database_ready
    from api_service.core.db import get_engine

    async def _db_check():
        return await check_database_ready(get_engine)

    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=_db_check,
    )
