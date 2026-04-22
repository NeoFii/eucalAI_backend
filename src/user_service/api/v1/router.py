"""User API v1 router."""

from fastapi import APIRouter

from user_service.api.v1.endpoints import auth, billing, internal, keys

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(keys.router)
api_router.include_router(internal.router)
