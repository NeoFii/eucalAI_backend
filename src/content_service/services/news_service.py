"""News domain service owned by the content service."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.snowflake import generate_snowflake_id
from common.utils.timezone import now
from content_service.models import News


class NewsService:
    """CRUD and query operations for the news domain."""

    @staticmethod
    async def create(
        db: AsyncSession,
        title: str,
        slug: str,
        content: str,
        summary: Optional[str] = None,
        cover_image: Optional[str] = None,
        status: int = 0,
        published_at: Optional[str] = None,
        author_id: Optional[int] = None,
    ) -> News:
        existing = await NewsService.get_by_slug(db, slug)
        if existing:
            raise ValueError(f"slug already exists: {slug}")

        resolved_published_at = published_at
        if status == 1 and not resolved_published_at:
            resolved_published_at = now()

        news = News(
            uid=generate_snowflake_id(),
            title=title,
            slug=slug,
            summary=summary,
            cover_image=cover_image,
            content=content,
            status=status,
            published_at=resolved_published_at,
            author_id=author_id,
        )
        db.add(news)
        await db.flush()
        await db.refresh(news)
        return news

    @staticmethod
    async def get_by_uid(db: AsyncSession, uid: int) -> Optional[News]:
        result = await db.execute(select(News).where(News.uid == uid))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[News]:
        result = await db.execute(select(News).where(News.slug == slug))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_published_by_slug(db: AsyncSession, slug: str) -> Optional[News]:
        result = await db.execute(
            select(News).where(
                News.slug == slug,
                News.status == 1,
                News.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 10,
        status: Optional[int] = None,
    ) -> tuple[list[News], int]:
        query = select(News)
        count_query = select(func.count(News.id))

        if status is not None:
            query = query.where(News.status == status)
            count_query = count_query.where(News.status == status)
        else:
            query = query.where(News.deleted_at.is_(None), News.status != 3)
            count_query = count_query.where(News.deleted_at.is_(None), News.status != 3)

        query = query.order_by(News.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        items = (await db.execute(query)).scalars().all()
        total = (await db.execute(count_query)).scalar() or 0
        return list(items), total

    @staticmethod
    async def list_published(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[News], int]:
        query = (
            select(News)
            .where(News.status == 1, News.deleted_at.is_(None))
            .order_by(News.published_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_query = select(func.count(News.id)).where(
            News.status == 1,
            News.deleted_at.is_(None),
        )
        items = (await db.execute(query)).scalars().all()
        total = (await db.execute(count_query)).scalar() or 0
        return list(items), total

    @staticmethod
    async def update(
        db: AsyncSession,
        uid: int,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        summary: Optional[str] = None,
        cover_image: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[int] = None,
        published_at: Optional[str] = None,
    ) -> News:
        news = await NewsService.get_by_uid(db, uid)
        if not news:
            raise ValueError("news not found")

        if slug and slug != news.slug:
            result = await db.execute(
                select(News).where(and_(News.slug == slug, News.uid != uid))
            )
            if result.scalar_one_or_none():
                raise ValueError(f"slug already exists: {slug}")

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
            if status == 1 and not news.published_at:
                news.published_at = now()
            news.status = status
        if published_at is not None:
            news.published_at = published_at

        await db.flush()
        await db.refresh(news)
        return news

    @staticmethod
    async def delete(db: AsyncSession, uid: int) -> News:
        news = await NewsService.get_by_uid(db, uid)
        if not news:
            raise ValueError("news not found")

        news.status = 2
        news.deleted_at = None
        news.deleted_by_admin_id = None
        await db.flush()
        await db.refresh(news)
        return news

    @staticmethod
    async def destroy(
        db: AsyncSession,
        uid: int,
        deleted_by_admin_id: Optional[int] = None,
    ) -> News:
        news = await NewsService.get_by_uid(db, uid)
        if not news:
            raise ValueError("news not found")

        news.status = 3
        news.deleted_at = now()
        news.deleted_by_admin_id = deleted_by_admin_id
        await db.flush()
        await db.refresh(news)
        return news
