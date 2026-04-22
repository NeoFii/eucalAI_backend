"""Admin API v1 router_service."""

from fastapi import APIRouter

from admin_service.api.v1.endpoints import (
    admin_audit_logs,
    admin_users,
    auth,
    internal,
    invitation,
    model_catalog,
    model_catalog_admin,
    user_management,
    vouchers,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_audit_logs.router)
api_router.include_router(invitation.router)
api_router.include_router(vouchers.router)
api_router.include_router(model_catalog.router)
api_router.include_router(model_catalog_admin.router, prefix="/admin")
api_router.include_router(internal.router)
api_router.include_router(user_management.router)
