"""Standalone user-service entrypoint for local development."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability

from user_service import db
from user_service.api.v1.router import api_router
from user_service.config import settings

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.create_engine(settings.DATABASE_URL)
    db.init_session_factory()
    logger.info("user-service started (standalone)")
    yield
    await db.close_db()
    logger.info("user-service stopped")


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


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check():
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(db.get_engine),
    )
