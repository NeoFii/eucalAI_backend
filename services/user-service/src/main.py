"""Standalone user-service entrypoint for local development."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.cache import close_cache_redis, init_cache_redis
from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.internal import build_internal_auth_dependency, close_internal_clients
from common.internal_logs import build_internal_logs_router
from common.observability import configure_logging_from_settings, install_observability, log_event
from common.redis import check_redis_ready, close_redis, init_redis
from core import db
from core.config import settings
from core.router import api_router

configure_logging_from_settings(settings)
logger = logging.getLogger(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DATABASE_ECHO,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    )
    db.init_session_factory()
    await init_redis(settings.REDIS_URL)
    await init_cache_redis(settings.CACHE_REDIS_URL)
    log_event(logger, logging.INFO, "service_started", service=settings.SERVICE_NAME)
    yield
    await close_internal_clients()
    await close_cache_redis()
    await close_redis()
    await db.close_db()
    log_event(logger, logging.INFO, "service_stopped", service=settings.SERVICE_NAME)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_observability(app, service_name=settings.SERVICE_NAME)
register_exception_handlers(app)
app.include_router(api_router)

_logs_auth = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"admin-service"},
)
app.include_router(build_internal_logs_router(_logs_auth))


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check():
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(db.get_engine),
        redis_check=check_redis_ready,
    )
