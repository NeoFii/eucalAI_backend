"""
新闻公开端点
提供新闻的公开读取接口（无需认证）
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.news import News
from user.dependencies import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["新闻"])


@router.get("/news")
async def list_news(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    language: Optional[str] = Query(None, description="语言: zh=中文 en=英文，默认返回全部"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取新闻列表（公开接口）
    仅返回已发布的新闻，按发布时间倒序
    支持按语言筛选
    """
    from sqlalchemy import select, func, and_

    # 查询已发布的新闻
    query = select(News).where(News.status == 1)

    # 语言筛选
    if language:
        query = query.where(News.language == language)

    # 按发布时间倒序
    query = query.order_by(News.published_at.desc())

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    news_list = result.scalars().all()

    # 计数
    count_query = select(func.count(News.id)).where(News.status == 1)
    if language:
        count_query = count_query.where(News.language == language)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "items": [
                {
                    "uid": news.uid,
                    "language": news.language,
                    "title": news.title,
                    "slug": news.slug,
                    "summary": news.summary,
                    "cover_image": news.cover_image,
                    "published_at": news.published_at.isoformat() if news.published_at else None,
                }
                for news in news_list
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/news/{slug}")
async def get_news(
    slug: str,
    language: Optional[str] = Query(None, description="语言: zh=中文 en=英文"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取新闻详情（公开接口）
    根据 slug 获取，仅返回已发布的新闻
    支持按语言筛选
    """
    from sqlalchemy import select, and_

    query = select(News).where(
        and_(
            News.slug == slug,
            News.status == 1
        )
    )
    if language:
        query = query.where(News.language == language)

    result = await db.execute(query)
    news = result.scalar_one_or_none()

    if not news:
        return {"code": 404, "message": "新闻不存在"}

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "uid": news.uid,
            "language": news.language,
            "title": news.title,
            "slug": news.slug,
            "summary": news.summary,
            "cover_image": news.cover_image,
            "content": news.content,
            "status": news.status,
            "published_at": news.published_at.isoformat() if news.published_at else None,
            "created_at": news.created_at.isoformat(),
            "updated_at": news.updated_at.isoformat(),
        },
    }
