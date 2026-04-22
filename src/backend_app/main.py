"""Backend-app entrypoint: aggregates admin / user into one FastAPI process.

Design notes:

- Each sub-service module keeps its own config + db + models + api, unchanged.
- We import the admin and user API routers and merge them.
- Lifespan sequentially initializes two database engines and runs the admin
  super-admin bootstrap.
- HMAC inter-service calls (admin<->user, etc.) still go over
  ``http://localhost:<PORT>`` to themselves. They remain wire-compatible with
  ``common/internal.py`` so rollback (deploying the three separate services
  again) needs no code changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from common.core.exception_handlers import register_exception_handlers
from common.health import build_readiness_response, check_database_ready
from common.observability import configure_logging, install_observability

from admin_service import db as admin_db
from admin_service.api.v1.endpoints import (
    admin_audit_logs as admin_audit_logs_endpoint,
    admin_users as admin_users_endpoint,
    auth as admin_auth_endpoint,
    internal as admin_internal_endpoint,
    invitation as admin_invitation_endpoint,
    user_management as user_management_endpoint,
)
from user_service.api.v1.endpoints import auth as user_auth_endpoint
from user_service.api.v1.endpoints import billing as user_billing_endpoint
from user_service.api.v1.endpoints import internal as user_internal_endpoint
from user_service.api.v1.endpoints import keys as user_keys_endpoint
from user_service import db as user_db

from backend_app.config import settings
from backend_app.lifecycle import build_lifecycle_manager

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)
lifecycle_manager = build_lifecycle_manager(logger=logger)


def _build_user_api_router() -> APIRouter:
    """Compose user-service routes."""
    router = APIRouter(prefix="/api/v1")
    router.include_router(user_auth_endpoint.router)
    router.include_router(user_billing_endpoint.router)
    router.include_router(user_keys_endpoint.router)
    # admin_billing removed: replaced by admin-service user_management endpoints
    router.include_router(user_internal_endpoint.router)
    return router


def _build_admin_public_api_router() -> APIRouter:
    """Admin public routes are mounted under ``/api/v1/admin`` to avoid colliding
    with user-service's ``/api/v1/auth/*``. This only shifts admin UI client
    URLs (admin/auth/login etc.); internal HMAC endpoints stay unmoved so that
    user clients keep working without changes.

    ``dashboard.py`` is intentionally omitted: it is legacy and ``/dashboard/
    stats`` is canonically served by ``invitation.py`` (which admin_service's
    own api_router also relies on).
    """
    router = APIRouter(prefix="/api/v1/admin")
    router.include_router(admin_auth_endpoint.router)
    router.include_router(admin_users_endpoint.router)
    router.include_router(admin_audit_logs_endpoint.router)
    router.include_router(admin_invitation_endpoint.router)
    router.include_router(user_management_endpoint.router)
    return router


def _build_admin_internal_api_router() -> APIRouter:
    """Admin internal HMAC endpoints remain at ``/api/v1/internal/admins`` and
    ``/api/v1/internal/invitation-codes`` so that HMAC callers in user
    services keep working without code changes.
    """
    router = APIRouter(prefix="/api/v1")
    router.include_router(admin_internal_endpoint.router)
    return router


user_api_router = _build_user_api_router()
admin_public_router = _build_admin_public_api_router()
admin_internal_router = _build_admin_internal_api_router()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifecycle_manager.lifespan,
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
# user. user is last so any residual collision with user's
# /api/v1/auth/* is surfaced by the route-uniqueness test instead of silently
# shadowed.
app.include_router(admin_public_router)
app.include_router(admin_internal_router)
app.include_router(user_api_router)


async def _check_all_databases() -> tuple[bool, dict[str, Any]]:
    """Run readiness probes for the active data-owning engines concurrently."""

    probes: list[Callable[[], Awaitable[tuple[bool, str | None]]]] = [
        lambda: check_database_ready(admin_db.get_engine),
        lambda: check_database_ready(user_db.get_engine),
    ]
    names = ["admin", "user"]

    results = await asyncio.gather(
        *(probe() for probe in probes),
        return_exceptions=True,
    )

    payload: dict[str, Any] = {}
    ready = True
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            ready = False
            payload[name] = {"ready": False, "error": str(result)}
        else:
            db_ready, detail = result
            ready = ready and db_ready
            payload[name] = {"ready": db_ready, "error": detail}
    return ready, payload


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
        "message": "Eucal AI Backend (admin + user)",
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
