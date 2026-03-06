"""
新闻服务
提供新闻的增删改查逻辑
"""

import logging
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.news import News
from common.utils.snowflake import generate_snowflake_id

logger = logging.getLogger(__name__)


class NewsService:
    """新闻服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        title: str,
        slug: str,
        content: str,
        language: str = "zh",
        summary: Optional[str] = None,
        cover_image: Optional[str] = None,
        status: int = 0,
        published_at: Optional[str] = None,
        author_id: Optional[int] = None,
    ) -> News:
        """创建新闻"""
        # 检查同一语言下 slug 是否已存在
        result = await db.execute(
            select(News).where(
                and_(News.language == language, News.slug == slug)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"该语言下 slug 已存在: {slug}")

        # 生成雪花 ID
        uid = generate_snowflake_id()

        # 如果是发布状态且没有发布时间，自动设置
        from common.utils.timezone import now
        pub_at = published_at
        if status == 1 and not pub_at:
            pub_at = now()

        news = News(
            uid=uid,
            language=language,
            title=title,
            slug=slug,
            summary=summary,
            cover_image=cover_image,
            content=content,
            status=status,
            published_at=pub_at,
            author_id=author_id,
        )
        db.add(news)
        await db.flush()
        await db.refresh(news)
        return news

    @staticmethod
    async def get_by_uid(db: AsyncSession, uid: int) -> Optional[News]:
        """根据 uid 获取新闻"""
        result = await db.execute(
            select(News).where(News.uid == uid)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str, language: Optional[str] = None) -> Optional[News]:
        """根据 slug 获取新闻，可按语言筛选"""
        query = select(News).where(News.slug == slug)
        if language:
            query = query.where(News.language == language)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 10,
        status: Optional[int] = None,
        language: Optional[str] = None,
    ) -> tuple[list[News], int]:
        """获取新闻列表"""
        query = select(News)
        count_query = select(func.count(News.id))

        if status is not None:
            query = query.where(News.status == status)
            count_query = count_query.where(News.status == status)

        if language:
            query = query.where(News.language == language)
            count_query = count_query.where(News.language == language)

        # 倒序排列
        query = query.order_by(News.created_at.desc())

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询
        result = await db.execute(query)
        items = result.scalars().all()

        # 计数
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(items), total

    @staticmethod
    async def update(
        db: AsyncSession,
        uid: int,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        language: Optional[str] = None,
        summary: Optional[str] = None,
        cover_image: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[int] = None,
        published_at: Optional[str] = None,
    ) -> News:
        """更新新闻"""
        news = await NewsService.get_by_uid(db, uid)
        if not news:
            raise ValueError("新闻不存在")

        # 如果修改了 slug 或 language，检查唯一性
        new_slug = slug or news.slug
        new_language = language or news.language
        if (slug and slug != news.slug) or (language and language != news.language):
            result = await db.execute(
                select(News).where(
                    and_(
                        News.language == new_language,
                        News.slug == new_slug,
                        News.uid != uid  # 排除自己
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise ValueError(f"该语言下 slug 已存在: {new_slug}")

        # 更新字段
        if language is not None:
            news.language = language
        if title is not None:
            news.title = title
        if slug is not None:
            news.slug = slug
        if summary is not None:
            news.summary = summary
        if cover_image is not None:
            news.cover_image = cover_image
        if content is not None:
            news.content = content
        if status is not None:
            # 如果是发布状态且没有发布时间，自动设置
            if status == 1 and not news.published_at:
                from common.utils.timezone import now
                news.published_at = now()
            news.status = status
        if published_at is not None:
            news.published_at = published_at

        await db.flush()
        await db.refresh(news)
        return news

    @staticmethod
    async def delete(db: AsyncSession, uid: int) -> News:
        """下线新闻（软删除）"""
        news = await NewsService.get_by_uid(db, uid)
        if not news:
            raise ValueError("新闻不存在")

        # 软删除：状态改为已下线
        news.status = 2
        await db.flush()
        await db.refresh(news)
        return news
