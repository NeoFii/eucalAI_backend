"""FastAPI application entry point for the unified api-service."""

from __future__ import annotations

import logging
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
    """Configure snowflake ID generator."""
    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )


registry.register("logging", init_fn=_init_logging, priority=0)
registry.register("snowflake", init_fn=_init_snowflake, priority=10)


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
    """Readiness probe — Phase 1 always returns ready.

    Phase 2 will replace this with build_readiness_response that checks
    database and Redis connectivity.
    """
    return {
        "status": "ready",
        "service": settings.SERVICE_NAME,
    }
