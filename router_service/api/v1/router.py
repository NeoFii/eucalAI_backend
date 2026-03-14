"""Router service API router_service."""

from fastapi import APIRouter

from router_service.api.v1.endpoints import billing, keys, openai_compat

api_router = APIRouter(redirect_slashes=False)
api_router.include_router(openai_compat.router)
api_router.include_router(billing.router, prefix="/api/v1")
api_router.include_router(keys.router, prefix="/api/v1")
