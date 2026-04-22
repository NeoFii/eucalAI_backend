"""Model catalog data-access methods."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from admin_service.models import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from common.db import BaseRepository


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


class SupportedModelRepository(BaseRepository[SupportedModel]):
    """Repository for supported models."""

    def __init__(self, session) -> None:
        super().__init__(session, SupportedModel)

    def _with_relationships(self):
        return self._base_query().options(
            selectinload(SupportedModel.vendor),
            selectinload(SupportedModel.category_links).selectinload(
                SupportedModelCategoryMap.category
            ),
        )

    async def get_by_slug(self, slug: str, *, active_only: bool) -> SupportedModel | None:
        statement = self._with_relationships().where(SupportedModel.slug == slug)
        if active_only:
            statement = statement.where(SupportedModel.is_active.is_(True))
            statement = statement.join(SupportedModel.vendor).where(ModelVendor.is_active.is_(True))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_models(
        self,
        *,
        page: int,
        page_size: int,
        active_only: bool,
        category: str | None = None,
        vendors: list[str] | None = None,
        q: str | None = None,
    ) -> tuple[list[SupportedModel], int]:
        statement = self._with_relationships().join(SupportedModel.vendor)
        if active_only:
            statement = statement.where(
                SupportedModel.is_active.is_(True),
                ModelVendor.is_active.is_(True),
            )
        if vendors:
            statement = statement.where(ModelVendor.slug.in_(vendors))
        if category:
            statement = (
                statement.join(SupportedModel.category_links)
                .join(SupportedModelCategoryMap.category)
                .where(ModelCategory.key == category)
            )
            if active_only:
                statement = statement.where(ModelCategory.is_active.is_(True))
        if q:
            pattern = f"%{q}%"
            statement = statement.where(
                or_(
                    SupportedModel.slug.ilike(pattern),
                    SupportedModel.name.ilike(pattern),
                    SupportedModel.description.ilike(pattern),
                )
            )

        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar() or 0)
        rows = await self.session.execute(
            statement.order_by(SupportedModel.sort_order.asc(), SupportedModel.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().unique().all()), total
