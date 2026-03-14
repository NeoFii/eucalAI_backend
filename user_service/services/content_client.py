"""Content-service clients used by user endpoints."""

from __future__ import annotations

import httpx

from user_service.config import settings

CONTENT_TIMEOUT_SECONDS = 5.0


class ContentPublicClientService:
    """Client for public content-service news endpoints."""

    @staticmethod
    async def list_news(*, page: int, page_size: int) -> dict:
        async with httpx.AsyncClient(timeout=CONTENT_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.CONTENT_SERVICE_URL.rstrip('/')}/api/v1/news",
                params={"page": page, "page_size": page_size},
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    async def get_news(slug: str) -> dict:
        async with httpx.AsyncClient(timeout=CONTENT_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.CONTENT_SERVICE_URL.rstrip('/')}/api/v1/news/{slug}",
            )
        response.raise_for_status()
        return response.json()
