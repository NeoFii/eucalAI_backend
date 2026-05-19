"""FastAPI application entry point for the unified api-service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_service.common.core.exception_handlers import register_exception_handlers
from api_service.relay.rate_limiter import RateLimitExceeded
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
    worker_id = os.getpid() % 32
    configure_snowflake(
        worker_id=worker_id,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
    log_event(
        logger,
        logging.INFO,
        "snowflake_configured",
        worker_id=worker_id,
        pid=os.getpid(),
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


# ── Phase 5: super-admin bootstrap (priority=25, after DB=20, before Redis=30) ──
async def _bootstrap_super_admin() -> None:
    """Idempotently create the bootstrap super admin if none exists.

    Wired at priority=25 so it runs AFTER the database engine is initialised
    (priority=20) but BEFORE Redis comes up (priority=30). Pitfall 6 — order
    matters because the bootstrap acquires a MySQL named lock and requires
    a live DB session.
    """
    from api_service.services.admin.bootstrap_service import AdminBootstrapService

    await AdminBootstrapService.ensure_super_admin()


registry.register(
    "super_admin_bootstrap",
    init_fn=_bootstrap_super_admin,
    priority=25,
)


async def _init_redis() -> None:
    """Initialize Redis db/0 pool (session/rate-limit)."""
    from api_service.common.infra.redis import init_redis

    await init_redis(settings.REDIS_URL)


async def _shutdown_redis() -> None:
    """Close Redis db/0 pool."""
    from api_service.common.infra.redis import close_redis

    await close_redis()


registry.register("redis", init_fn=_init_redis, shutdown_fn=_shutdown_redis, priority=30)


async def _init_cache_redis() -> None:
    """Initialize Cache Redis db/2 pool."""
    from api_service.common.infra.cache import init_cache_redis

    await init_cache_redis(settings.CACHE_REDIS_URL)


async def _shutdown_cache_redis() -> None:
    """Close Cache Redis db/2 pool."""
    from api_service.common.infra.cache import close_cache_redis

    await close_cache_redis()


registry.register(
    "cache_redis", init_fn=_init_cache_redis, shutdown_fn=_shutdown_cache_redis, priority=30
)


async def _init_arq_pool() -> None:
    """Initialize ARQ Redis pool (db/1) for enqueueing background jobs."""
    from api_service.core.arq_pool import init_arq_pool

    await init_arq_pool()


async def _shutdown_arq_pool() -> None:
    """Close ARQ Redis pool."""
    from api_service.core.arq_pool import close_arq_pool

    await close_arq_pool()


registry.register(
    "arq_pool", init_fn=_init_arq_pool, shutdown_fn=_shutdown_arq_pool, priority=40
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


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc: RateLimitExceeded):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"error": {"message": exc.message, "type": "rate_limit_error"}},
        headers={"Retry-After": str(exc.retry_after)},
    )

# ── Routes ───────────────────────────────────────────────────────────────────

app.include_router(api_router)

# Phase 7: Relay routes mounted at app root (not under /api/v1 prefix)
from api_service.controllers.relay import relay_router  # noqa: E402

app.include_router(relay_router)


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
    """Readiness probe — checks database, Redis db/0, and Cache Redis db/2."""
    from api_service.common.health import build_readiness_response, check_database_ready
    from api_service.common.infra.cache import check_cache_redis_ready
    from api_service.common.infra.redis import check_redis_ready
    from api_service.core.db import get_engine

    async def _db_check():
        return await check_database_ready(get_engine)

    async def _combined_redis_check() -> tuple[bool, str | None]:
        ok, err = await check_redis_ready()
        if not ok:
            return False, f"Redis db/0: {err}"
        ok, err = await check_cache_redis_ready()
        if not ok:
            return False, f"Cache Redis db/2: {err}"
        return True, None

    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=_db_check,
        redis_check=_combined_redis_check,
    )
