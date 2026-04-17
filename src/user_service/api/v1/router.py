"""User API v1 router_service."""

from fastapi import APIRouter

from user_service.api.v1.endpoints import auth, internal, news

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(internal.router)
api_router.include_router(news.router)
