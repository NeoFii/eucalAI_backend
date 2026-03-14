"""User service entrypoint."""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability, log_event
from user_service.db import close_db, create_engine, get_engine, init_db, init_session_factory
from common.utils.snowflake import configure_snowflake
from user_service.api import api_router
from user_service.config import settings
from user_service.models import SERVICE_MODELS

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize user-service infrastructure."""
    log_event(logger, logging.INFO, "service_starting", service=settings.SERVICE_NAME)

    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
    create_engine(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DATABASE_ECHO,
    )
    init_session_factory()
    if settings.AUTO_INIT_DB:
        await init_db(SERVICE_MODELS)
        log_event(logger, logging.INFO, "schema_auto_init_enabled", service=settings.SERVICE_NAME)
    else:
        log_event(logger, logging.INFO, "schema_auto_init_skipped", service=settings.SERVICE_NAME)

    log_event(logger, logging.INFO, "service_started", service=settings.SERVICE_NAME, port=settings.PORT)
    yield
    log_event(logger, logging.INFO, "service_stopping", service=settings.SERVICE_NAME)
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
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check():
    """Readiness endpoint."""
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(get_engine),
    )


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Eucal AI User Service",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "user_service.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
