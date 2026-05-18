"""Model catalog data-access methods."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from api_service.common.infra.db.repository import BaseRepository
from api_service.models import (
    ModelCategory,
    ModelCatalog,
    ModelCatalogCategoryMap,
    ModelVendor,
)


class ModelVendorRepository(BaseRepository[ModelVendor]):
    """Repository for model vendors."""

    def __init__(self, session) -> None:
        super().__init__(session, ModelVendor)

    async def get_by_slug(self, slug: str) -> ModelVendor | None:
        return await self.find_one(ModelVendor.slug == slug)

    async def list_vendors(
        self,
        *,
        page: int,
        page_size: int,
        active_only: bool,
    ) -> tuple[list[ModelVendor], int]:
        statement = self._base_query()
        if active_only:
            statement = statement.where(ModelVendor.is_active.is_(True))
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(statement.subquery()))
            ).scalar()
            or 0
        )
        rows = await self.session.execute(
            statement.order_by(ModelVendor.sort_order.asc(), ModelVendor.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total


class ModelCategoryRepository(BaseRepository[ModelCategory]):
    """Repository for model categories."""

    def __init__(self, session) -> None:
        super().__init__(session, ModelCategory)

    async def get_by_key(self, key: str) -> ModelCategory | None:
        return await self.find_one(ModelCategory.key == key)

    async def list_categories(
        self,
        *,
        page: int,
        page_size: int,
        active_only: bool,
    ) -> tuple[list[ModelCategory], int]:
        statement = self._base_query()
        if active_only:
            statement = statement.where(ModelCategory.is_active.is_(True))
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(statement.subquery()))
            ).scalar()
            or 0
        )
        rows = await self.session.execute(
            statement.order_by(ModelCategory.sort_order.asc(), ModelCategory.key.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total


class ModelCatalogRepository(BaseRepository[ModelCatalog]):
    """Repository for model catalog entries."""

    def __init__(self, session) -> None:
        super().__init__(session, ModelCatalog)

    def _with_relationships(self):
        return self._base_query().options(
            selectinload(ModelCatalog.vendor),
            selectinload(ModelCatalog.category_links).selectinload(
                ModelCatalogCategoryMap.category
            ),
        )

    async def get_by_slug(self, slug: str, *, active_only: bool) -> ModelCatalog | None:
        statement = self._with_relationships().where(ModelCatalog.slug == slug)
        if active_only:
            statement = statement.where(ModelCatalog.is_active.is_(True))
            statement = statement.join(ModelCatalog.vendor).where(ModelVendor.is_active.is_(True))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_models(
        self,
        *,
        page: int,
        page_size: int,
        active_only: bool,
        status: str | None = None,
        category: str | None = None,
        vendors: list[str] | None = None,
        q: str | None = None,
    ) -> tuple[list[ModelCatalog], int]:
        statement = self._with_relationships().join(ModelCatalog.vendor)
        if status == "active":
            statement = statement.where(
                ModelCatalog.is_active.is_(True),
                ModelVendor.is_active.is_(True),
            )
        elif status == "archived":
            statement = statement.where(ModelCatalog.is_active.is_(False))
        elif status == "all":
            pass
        elif active_only:
            statement = statement.where(
                ModelCatalog.is_active.is_(True),
                ModelVendor.is_active.is_(True),
            )
        if vendors:
            statement = statement.where(ModelVendor.slug.in_(vendors))
        if category:
            statement = (
                statement.join(ModelCatalog.category_links)
                .join(ModelCatalogCategoryMap.category)
                .where(ModelCategory.key == category)
            )
            if status == "active" or (status is None and active_only):
                statement = statement.where(ModelCategory.is_active.is_(True))
        if q:
            pattern = f"%{q}%"
            statement = statement.where(
                or_(
                    ModelCatalog.slug.ilike(pattern),
                    ModelCatalog.name.ilike(pattern),
                    ModelCatalog.summary.ilike(pattern),
                    ModelCatalog.description.ilike(pattern),
                )
            )

        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar() or 0)
        rows = await self.session.execute(
            statement.order_by(ModelCatalog.sort_order.asc(), ModelCatalog.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().unique().all()), total

    async def get_routing_slugs_existing(self, slugs: list[str]) -> set[str]:
        if not slugs:
            return set()
        result = await self.session.execute(
            select(ModelCatalog.routing_slug).where(
                ModelCatalog.routing_slug.in_(slugs),
                ModelCatalog.is_active.is_(True),
            )
        )
        return {row[0] for row in result.all()}
