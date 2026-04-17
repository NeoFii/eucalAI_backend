"""Backend-app entrypoint: aggregates admin / user / content / testing into one FastAPI process.

Design notes:

- Each sub-service module keeps its own config + db + models + api, unchanged.
- We import the four api_routers and merge them, except we rebuild the user
  router to exclude the ``news`` proxy (content-service exposes the canonical
  ``/api/v1/news``; the proxy would collide).
- Lifespan sequentially initializes four database engines and runs the admin
  super-admin bootstrap. The testing-service apscheduler is intentionally NOT
  started here; ``testing-scheduler`` (a separate process) owns it.
- HMAC inter-service calls (admin<->user, user<->content, etc.) still go over
  ``http://localhost:<PORT>`` to themselves. They remain wire-compatible with
  ``common/internal.py`` so rollback (deploying the four separate services
  again) needs no code changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability, log_event
from common.utils.snowflake import configure_snowflake

from admin_service import db as admin_db
from admin_service.api.v1.endpoints import (
    admin_audit_logs as admin_audit_logs_endpoint,
    admin_users as admin_users_endpoint,
    auth as admin_auth_endpoint,
    internal as admin_internal_endpoint,
    invitation as admin_invitation_endpoint,
)
from admin_service.config import settings as admin_settings
from admin_service.models import SERVICE_MODELS as ADMIN_MODELS
from admin_service.services.bootstrap_service import AdminBootstrapService

from user_service import db as user_db
from user_service.api.v1.endpoints import auth as user_auth_endpoint
from user_service.api.v1.endpoints import internal as user_internal_endpoint
from user_service.config import settings as user_settings
from user_service.models import SERVICE_MODELS as USER_MODELS

from content_service import db as content_db
from content_service.api import api_router as content_api_router
from content_service.config import settings as content_settings
from content_service.models import SERVICE_MODELS as CONTENT_MODELS

from testing_service import db as testing_db
from testing_service.api import api_router as testing_api_router
from testing_service.config import get_settings as get_testing_settings
from testing_service.models import SERVICE_MODELS as TESTING_MODELS

from backend_app.config import settings

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)

testing_settings = get_testing_settings()


def _build_user_api_router_without_news() -> APIRouter:
    """Compose user-service routes, deliberately omitting the news proxy.

    content-service owns ``/api/v1/news`` directly; including user-service's
    proxy would cause a path collision in the merged app.
    """
    router = APIRouter(prefix="/api/v1")
    router.include_router(user_auth_endpoint.router)
    router.include_router(user_internal_endpoint.router)
    return router


def _build_admin_public_api_router() -> APIRouter:
    """Admin public routes are mounted under ``/api/v1/admin`` to avoid colliding
    with user-service's ``/api/v1/auth/*``. This only shifts admin UI client
    URLs (admin/auth/login etc.); internal HMAC endpoints stay unmoved so that
    content/testing/user clients keep working without changes.

    ``dashboard.py`` is intentionally omitted: it is legacy and ``/dashboard/
    stats`` is canonically served by ``invitation.py`` (which admin_service's
    own api_router also relies on).
    """
    router = APIRouter(prefix="/api/v1/admin")
    router.include_router(admin_auth_endpoint.router)
    router.include_router(admin_users_endpoint.router)
    router.include_router(admin_audit_logs_endpoint.router)
    router.include_router(admin_invitation_endpoint.router)
    return router


def _build_admin_internal_api_router() -> APIRouter:
    """Admin internal HMAC endpoints remain at ``/api/v1/internal/admins`` and
    ``/api/v1/internal/invitation-codes`` so that HMAC callers in content/
    testing/user services keep working without code changes.
    """
    router = APIRouter(prefix="/api/v1")
    router.include_router(admin_internal_endpoint.router)
    return router


user_api_router_no_news = _build_user_api_router_without_news()
admin_public_router = _build_admin_public_api_router()
admin_internal_router = _build_admin_internal_api_router()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot four DB engines + admin superadmin bootstrap in fixed order."""
    del app
    log_event(logger, logging.INFO, "service_starting", service=settings.SERVICE_NAME)

    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )

    admin_db.create_engine(
        database_url=admin_settings.DATABASE_URL,
        pool_size=admin_settings.DATABASE_POOL_SIZE,
        max_overflow=admin_settings.DATABASE_MAX_OVERFLOW,
        echo=admin_settings.DATABASE_ECHO,
    )
    admin_db.init_session_factory()

    user_db.create_engine(
        database_url=user_settings.DATABASE_URL,
        pool_size=user_settings.DATABASE_POOL_SIZE,
        max_overflow=user_settings.DATABASE_MAX_OVERFLOW,
        echo=user_settings.DATABASE_ECHO,
    )
    user_db.init_session_factory()

    content_db.create_engine(
        database_url=content_settings.DATABASE_URL,
        pool_size=content_settings.DATABASE_POOL_SIZE,
        max_overflow=content_settings.DATABASE_MAX_OVERFLOW,
        echo=content_settings.DATABASE_ECHO,
    )
    content_db.init_session_factory()

    testing_db.create_engine(
        database_url=testing_settings.DATABASE_URL,
        pool_size=testing_settings.DATABASE_POOL_SIZE,
        max_overflow=testing_settings.DATABASE_MAX_OVERFLOW,
        echo=testing_settings.DATABASE_ECHO,
    )
    testing_db.init_session_factory()

    if admin_settings.AUTO_INIT_DB:
        await admin_db.init_db(ADMIN_MODELS)
    if user_settings.AUTO_INIT_DB:
        await user_db.init_db(USER_MODELS)
    if content_settings.AUTO_INIT_DB:
        await content_db.init_db(CONTENT_MODELS)
    if testing_settings.auto_init_db:
        await testing_db.init_db(TESTING_MODELS)

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

    if testing_settings.probe_scheduler_enabled:
        log_event(
            logger,
            logging.WARNING,
            "probe_scheduler_flag_ignored_in_backend_app",
            service=settings.SERVICE_NAME,
            note="testing-scheduler must run as a separate process",
        )

    log_event(
        logger,
        logging.INFO,
        "service_started",
        service=settings.SERVICE_NAME,
        port=settings.PORT,
        domains=["admin", "user", "content", "testing"],
    )
    try:
        yield
    finally:
        log_event(logger, logging.INFO, "service_stopping", service=settings.SERVICE_NAME)
        await testing_db.close_db()
        await content_db.close_db()
        await user_db.close_db()
        await admin_db.close_db()


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

# Order: admin (public under /api/v1/admin + internal at /api/v1/internal) ->
# content -> testing -> user(no news). user is last so any residual collision
# with user's /api/v1/auth/* is surfaced by the route-uniqueness test instead
# of silently shadowed.
app.include_router(admin_public_router)
app.include_router(admin_internal_router)
app.include_router(content_api_router)
app.include_router(testing_api_router)
app.include_router(user_api_router_no_news)


async def _check_all_databases() -> dict[str, Any]:
    """Run readiness probes for all four engines concurrently."""

    probes: list[Callable[[], Awaitable[dict[str, Any]]]] = [
        lambda: check_database_ready(admin_db.get_engine),
        lambda: check_database_ready(user_db.get_engine),
        lambda: check_database_ready(content_db.get_engine),
        lambda: check_database_ready(testing_db.get_engine),
    ]
    names = ["admin", "user", "content", "testing"]

    results = await asyncio.gather(
        *(probe() for probe in probes),
        return_exceptions=True,
    )

    payload: dict[str, Any] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            payload[name] = {"ready": False, "error": str(result)}
        else:
            payload[name] = result
    return payload


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": settings.SERVICE_NAME, "version": settings.VERSION}


@app.get("/ready", tags=["health"])
async def readiness_check():
    return await build_readiness_response(
        service_name=settings.SERVICE_NAME,
        database_check=_check_all_databases,
    )


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "Eucal AI Backend (admin + user + content + testing)",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend_app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
