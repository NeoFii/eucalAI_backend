"""Admin service FastAPI entrypoint."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from admin_service.api import api_router
from admin_service.config import settings
from admin_service.db import close_db, create_engine, get_engine, init_session_factory
from admin_service.services.bootstrap_service import AdminBootstrapService
from common.db import ensure_database_at_head
from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability, log_event
from common.redis import check_redis_ready, close_redis, init_redis
from common.utils.snowflake import configure_snowflake

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage admin service startup and shutdown."""
    del app
    log_event(logger, logging.INFO, "service_starting", service=settings.SERVICE_NAME)

    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
    await init_redis(settings.REDIS_URL)
    create_engine(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DATABASE_ECHO,
    )
    init_session_factory()
    await ensure_database_at_head(service_name="admin-service", url=settings.DATABASE_URL)
    log_event(logger, logging.INFO, "schema_revision_verified", service=settings.SERVICE_NAME)

    bootstrap_created = await AdminBootstrapService.ensure_super_admin()
    log_event(
        logger,
        logging.INFO,
        "super_admin_bootstrap_completed",
        service=settings.SERVICE_NAME,
        created=bootstrap_created,
        enabled=settings.BOOTSTRAP_SUPERADMIN_ENABLED,
        required=settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP,
    )

    yield

    log_event(logger, logging.INFO, "service_stopping", service=settings.SERVICE_NAME)
    await close_redis()
    await close_db()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
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


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check():
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(get_engine),
        redis_check=check_redis_ready,
    )


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "Eucal AI Admin Service",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "admin_service.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
