# -*- coding: utf-8 -*-
"""Testing service entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.db import ensure_database_at_head
from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability, log_event
from common.utils.snowflake import configure_snowflake
from testing_service.db import close_db, create_engine, get_engine, init_session_factory
from testing_service.api.v1.router import api_router
from testing_service.config import get_settings

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize testing infrastructure without cross-service schema creation."""
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
    await ensure_database_at_head(service_name="testing-service", url=settings.DATABASE_URL)
    log_event(logger, logging.INFO, "schema_revision_verified", service=settings.SERVICE_NAME)

    instance_role = "scheduler" if settings.probe_scheduler_enabled else "api"
    log_event(
        logger,
        logging.INFO,
        "service_role_selected",
        service=settings.SERVICE_NAME,
        role=instance_role,
    )

    scheduler = None
    if settings.probe_enabled and settings.probe_scheduler_enabled:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from testing_service.benchmark.jobs import enqueue_scheduled_benchmark

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            enqueue_scheduled_benchmark,
            trigger=CronTrigger(hour=settings.probe_cron_hours, minute=0),
            id="probe_all_active",
            name="Scheduled probe for active offerings",
            replace_existing=True,
        )
        scheduler.start()
        log_event(
            logger,
            logging.INFO,
            "scheduled_probing_enabled",
            service=settings.SERVICE_NAME,
            hours=settings.probe_cron_hours,
        )
    elif not settings.probe_enabled:
        log_event(
            logger,
            logging.INFO,
            "scheduled_probing_disabled",
            service=settings.SERVICE_NAME,
            reason="probe_enabled=false",
        )
    else:
        log_event(
            logger,
            logging.INFO,
            "scheduled_probing_disabled",
            service=settings.SERVICE_NAME,
            reason="probe_scheduler_enabled=false",
        )

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
        log_event(logger, logging.INFO, "probe_scheduler_stopped", service=settings.SERVICE_NAME)
    log_event(logger, logging.INFO, "service_stopping", service=settings.SERVICE_NAME)
    await close_db()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
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
    """Health check."""
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready")
async def readiness_check():
    """Readiness endpoint."""
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=lambda: check_database_ready(get_engine),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "testing_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.DEBUG,
    )
