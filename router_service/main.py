"""Router service entrypoint."""

from __future__ import annotations

import asyncio
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
from router_service.db import close_db, create_engine, get_db_context, get_engine, init_db, init_session_factory
from common.utils.snowflake import configure_snowflake
from router_service.api import api_router
from router_service.config import settings
from router_service.models import SERVICE_MODELS
from router_service.services import RouterBillingService

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)


async def _release_stale_reservations_once() -> int:
    async with get_db_context() as db:
        return await RouterBillingService.release_stale_reservations(
            db,
            max_age_seconds=settings.ROUTER_PENDING_RESERVATION_MAX_AGE_SECONDS,
        )


def _log_stale_release_result(released: int) -> None:
    if not released:
        return
    log_event(
        logger,
        logging.WARNING,
        "stale_router_reservations_released",
        service=settings.SERVICE_NAME,
        released=released,
        max_age_seconds=settings.ROUTER_PENDING_RESERVATION_MAX_AGE_SECONDS,
    )


async def _run_stale_reservation_sweeper(stop_event: asyncio.Event) -> None:
    interval = settings.ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS
    if interval <= 0:
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            try:
                released = await _release_stale_reservations_once()
            except Exception:
                log_event(
                    logger,
                    logging.ERROR,
                    "stale_router_reservation_sweep_failed",
                    service=settings.SERVICE_NAME,
                )
            else:
                _log_stale_release_result(released)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize router infrastructure without cross-service schema creation."""
    del app
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

    released = await _release_stale_reservations_once()
    _log_stale_release_result(released)

    stop_event = asyncio.Event()
    sweeper_task = None
    if settings.ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS > 0:
        sweeper_task = asyncio.create_task(
            _run_stale_reservation_sweeper(stop_event),
            name="router-stale-reservation-sweeper",
        )
        log_event(
            logger,
            logging.INFO,
            "stale_router_reservation_sweeper_started",
            service=settings.SERVICE_NAME,
            interval_seconds=settings.ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS,
        )
    log_event(logger, logging.INFO, "service_started", service=settings.SERVICE_NAME, port=settings.PORT)
    yield
    stop_event.set()
    if sweeper_task is not None:
        await sweeper_task
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready")
async def readiness_check():
    """Readiness endpoint."""
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(get_engine),
    )


@app.get("/")
async def root():
    """Root metadata endpoint."""
    return {
        "message": "Eucal AI Router Service",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "router_service.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
