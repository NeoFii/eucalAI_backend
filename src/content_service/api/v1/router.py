"""Content service API router."""

from fastapi import APIRouter

from content_service.api.v1.endpoints import admin_news, news

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(news.router)
api_router.include_router(admin_news.router)
