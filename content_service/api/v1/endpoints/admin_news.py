"""Admin-facing news management endpoints owned by content-service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.api.dependencies import AdminPrincipal, get_current_admin, get_db_session
from content_service.schemas import (
    BaseResponse,
    CreateNewsRequest,
    DestroyNewsRequest,
    NewsData,
    NewsListItem,
    NewsListResponse,
    NewsListResponseData,
    NewsResponse,
    UpdateNewsRequest,
)
from content_service.services import NewsService

router = APIRouter(prefix="/admin/news", tags=["admin-news"])


def _to_news_data(news) -> NewsData:
    return NewsData(
        uid=str(news.uid),
        language=getattr(news, "language", None),
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


def _to_news_list_item(news) -> NewsListItem:
    return NewsListItem(
        uid=str(news.uid),
        language=getattr(news, "language", None),
        title=news.title,
        slug=news.slug,
        summary=news.summary,
        cover_image=news.cover_image,
        status=news.status,
        published_at=news.published_at,
        created_at=news.created_at,
        updated_at=news.updated_at,
    )


@router.post("", response_model=NewsResponse, summary="Create news")
async def create_news(
    request: CreateNewsRequest,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    try:
        news = await NewsService.create(
            db=db,
            title=request.title,
            slug=request.slug,
            content=request.content,
            summary=request.summary,
            cover_image=request.cover_image,
            status=request.status,
            published_at=request.published_at,
            author_id=current_admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NewsResponse(data=_to_news_data(news))


@router.get("", response_model=NewsListResponse, summary="List news")
async def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: int | None = Query(None),
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsListResponse:
    del current_admin
    news_list, total = await NewsService.list(db=db, page=page, page_size=page_size, status=status)
    return NewsListResponse(
        data=NewsListResponseData(
            items=[_to_news_list_item(news) for news in news_list],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{uid}", response_model=NewsResponse, summary="Get news")
async def get_news(
    uid: int,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    del current_admin
    news = await NewsService.get_by_uid(db, uid)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return NewsResponse(data=_to_news_data(news))


@router.put("/{uid}", response_model=NewsResponse, summary="Update news")
async def update_news(
    uid: int,
    request: UpdateNewsRequest,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    del current_admin
    try:
        news = await NewsService.update(
            db=db,
            uid=uid,
            title=request.title,
            slug=request.slug,
            summary=request.summary,
            cover_image=request.cover_image,
            content=request.content,
            status=request.status,
            published_at=request.published_at,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "news not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return NewsResponse(data=_to_news_data(news))


@router.delete("/{uid}", response_model=BaseResponse, summary="Delete news")
async def delete_news(
    uid: int,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> BaseResponse:
    del current_admin
    try:
        await NewsService.delete(db, uid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BaseResponse()


@router.delete("/{uid}/destroy", response_model=BaseResponse, summary="Destroy news")
async def destroy_news(
    uid: int,
    payload: DestroyNewsRequest,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> BaseResponse:
    try:
        await NewsService.destroy(
            db,
            uid,
            deleted_by_admin_id=payload.deleted_by_admin_id or current_admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BaseResponse()
