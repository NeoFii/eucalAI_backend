"""Admin API v1 router_service."""

from fastapi import APIRouter

from controllers import (
    admin_audit_logs,
    admin_users,
    auth,
    dashboard,
    internal,
    model_catalog,
    model_catalog_admin,
    pools,
    routing_config,
    routing_settings,
    service_logs,
    user_management,
    vouchers,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_audit_logs.router)
api_router.include_router(vouchers.router)
api_router.include_router(model_catalog.router)
api_router.include_router(model_catalog_admin.router, prefix="/admin")
api_router.include_router(routing_config.router, prefix="/admin")
api_router.include_router(routing_settings.router, prefix="/admin")
api_router.include_router(pools.router, prefix="/admin")
api_router.include_router(service_logs.router, prefix="/admin")
api_router.include_router(internal.router)
api_router.include_router(user_management.router)
api_router.include_router(dashboard.router)
