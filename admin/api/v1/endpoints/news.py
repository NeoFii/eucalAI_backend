"""
新闻管理端点
提供新闻的 CRUD 接口
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin.dependencies import get_current_admin, get_db_session
from admin.models import AdminUser, News
from admin.schemas import (
    AdminBaseResponse,
    CreateNewsRequest,
    NewsData,
    NewsListItem,
    NewsListResponse,
    NewsListResponseData,
    NewsResponse,
    UpdateNewsRequest,
)
from admin.services.news_service import NewsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["新闻管理"])


@router.post(
    "/",
    response_model=NewsResponse,
    summary="创建新闻",
    description="创建新的新闻",
)
async def create_news(
    request: CreateNewsRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    """创建新闻"""
    try:
        news = await NewsService.create(
            db=db,
            title=request.title,
            slug=request.slug,
            language=request.language,
            content=request.content,
            summary=request.summary,
            cover_image=request.cover_image,
            status=request.status,
            published_at=request.published_at,
            author_id=current_admin.id,
        )

        return NewsResponse(
            code=200,
            message="创建成功",
            data=NewsData(
                uid=news.uid,
                language=news.language,
                title=news.title,
                slug=news.slug,
                summary=news.summary,
                cover_image=news.cover_image,
                content=news.content,
                status=news.status,
                published_at=news.published_at,
                created_at=news.created_at,
                updated_at=news.updated_at,
            ),
        )
    except ValueError as e:
        return NewsResponse(code=400, message=str(e))


@router.get(
    "/",
    response_model=NewsListResponse,
    summary="获取新闻列表",
    description="分页获取新闻列表（管理端，返回全部状态）",
)
async def list_news(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[int] = Query(None, description="状态过滤：0=草稿 1=已发布 2=已下线"),
    language: Optional[str] = Query(None, description="语言过滤：zh=中文 en=英文"),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsListResponse:
    """获取新闻列表"""
    news_list, total = await NewsService.list(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        language=language,
    )

    return NewsListResponse(
        code=200,
        message="获取成功",
        data=NewsListResponseData(
            items=[
                NewsListItem(
                    uid=str(news.uid),
                    language=news.language,
                    title=news.title,
                    slug=news.slug,
                    summary=news.summary,
                    cover_image=news.cover_image,
                    status=news.status,
                    published_at=news.published_at,
                    created_at=news.created_at,
                    updated_at=news.updated_at,
                )
                for news in news_list
            ],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{uid}",
    response_model=NewsResponse,
    summary="获取新闻详情",
    description="根据 uid 获取新闻详情",
)
async def get_news(
    uid: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    """获取新闻详情"""
    try:
        uid_int = int(uid)
    except ValueError:
        return NewsResponse(code=400, message="无效的uid格式")

    news = await NewsService.get_by_uid(db, uid_int)
    if not news:
        return NewsResponse(code=404, message="新闻不存在")

    return NewsResponse(
        code=200,
        message="获取成功",
        data=NewsData(
            uid=str(news.uid),
            language=news.language,
            title=news.title,
            slug=news.slug,
            summary=news.summary,
            cover_image=news.cover_image,
            content=news.content,
            status=news.status,
            published_at=news.published_at,
            created_at=news.created_at,
            updated_at=news.updated_at,
        ),
    )


@router.put(
    "/{uid}",
    response_model=NewsResponse,
    summary="更新新闻",
    description="更新新闻内容",
)
async def update_news(
    uid: str,
    request: UpdateNewsRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> NewsResponse:
    """更新新闻"""
    try:
        uid_int = int(uid)
    except ValueError:
        return NewsResponse(code=400, message="无效的uid格式")

    try:
        news = await NewsService.update(
            db=db,
            uid=uid_int,
            title=request.title,
            slug=request.slug,
            language=request.language,
            summary=request.summary,
            cover_image=request.cover_image,
            content=request.content,
            status=request.status,
            published_at=request.published_at,
        )

        return NewsResponse(
            code=200,
            message="更新成功",
            data=NewsData(
                uid=news.uid,
                language=news.language,
                title=news.title,
                slug=news.slug,
                summary=news.summary,
                cover_image=news.cover_image,
                content=news.content,
                status=news.status,
                published_at=news.published_at,
                created_at=news.created_at,
                updated_at=news.updated_at,
            ),
        )
    except ValueError as e:
        return NewsResponse(code=400, message=str(e))


@router.delete(
    "/{uid}",
    response_model=AdminBaseResponse,
    summary="下线新闻",
    description="将新闻状态改为已下线（软删除）",
)
async def delete_news(
    uid: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminBaseResponse:
    """下线新闻"""
    try:
        uid_int = int(uid)
    except ValueError:
        return AdminBaseResponse(code=400, message="无效的uid格式")

    try:
        await NewsService.delete(db, uid_int)
        return AdminBaseResponse(code=200, message="已下线")
    except ValueError as e:
        return AdminBaseResponse(code=404, message=str(e))
