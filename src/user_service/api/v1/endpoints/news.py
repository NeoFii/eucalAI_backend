"""Public news endpoints."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from user_service.services.content_client import ContentPublicClientService

router = APIRouter(tags=["news"])


@router.get("/news")
async def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        return await ContentPublicClientService.list_news(page=page, page_size=page_size)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Content service request failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Content service unavailable") from exc


@router.get("/news/{slug}")
async def get_news(slug: str):
    try:
        return await ContentPublicClientService.get_news(slug)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="News not found") from exc
        raise HTTPException(status_code=exc.response.status_code, detail="Content service request failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Content service unavailable") from exc