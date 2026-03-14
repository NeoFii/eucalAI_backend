"""Public news endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.dependencies import get_db_session
from content_service.schemas import PublicNewsData, PublicNewsListItem
from content_service.services import NewsService

router = APIRouter(tags=["news"])


@router.get("/news")
async def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    news_list, total = await NewsService.list_published(db, page=page, page_size=page_size)
    items = [
        PublicNewsListItem(
            uid=news.uid,
            title=news.title,
            slug=news.slug,
            summary=news.summary,
            cover_image=news.cover_image,
            published_at=news.published_at,
        )
        for news in news_list
    ]
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [item.model_dump() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/news/{slug}")
async def get_news(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
):
    news = await NewsService.get_published_by_slug(db, slug)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")

    data = PublicNewsData(
        uid=news.uid,
        title=news.title,
        slug=news.slug,
        summary=news.summary,
        cover_image=news.cover_image,
        content=news.content,
        status=news.status,
        published_at=news.published_at,
        created_at=news.created_at,
        updated_at=news.updated_at,
    )
    return {
        "code": 200,
        "message": "success",
        "data": data.model_dump(),
    }