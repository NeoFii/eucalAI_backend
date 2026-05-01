"""User API v1 router."""

from fastapi import APIRouter

from controllers import (
    auth,
    billing,
    internal,
    internal_call_logs,
    internal_dashboard,
    internal_usage,
    internal_user_mgmt,
    internal_vouchers,
    keys,
    model_catalog,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(keys.router)
api_router.include_router(model_catalog.router)
api_router.include_router(internal.router)
api_router.include_router(internal_user_mgmt.router)
api_router.include_router(internal_vouchers.router)
api_router.include_router(internal_dashboard.router)
api_router.include_router(internal_usage.router)
api_router.include_router(internal_call_logs.router)
