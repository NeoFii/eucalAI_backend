"""Repositories for pools, pool_models, and pool_accounts."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.enums import PoolAccountStatus
from models.pool import Pool, PoolAccount, PoolModel
from common.db.query import ListParams
from common.db.repository import BaseRepository


class PoolRepository(BaseRepository[Pool]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Pool)

    async def get_by_slug(self, slug: str) -> Pool | None:
        return (
            await self.session.execute(
                select(Pool)
                .options(selectinload(Pool.models), selectinload(Pool.accounts))
                .where(Pool.slug == slug)
            )
        ).scalar_one_or_none()

    async def list_pools(
        self, *, page: int = 1, page_size: int = 50,
    ) -> tuple[list[Pool], int]:
        result = await self.get_list(
            ListParams(page=page, page_size=page_size, order_by="priority", order_dir="desc"),
            options=[selectinload(Pool.models), selectinload(Pool.accounts)],
        )
        return list(result.items), result.total

    async def get_active_for_routing(
        self, model_slugs: Sequence[str],
    ) -> list[tuple[Pool, PoolModel, PoolAccount]]:
        """Return (pool, pool_model, pool_account) triples for active routing."""
        if not model_slugs:
            return []
        rows = await self.session.execute(
            select(Pool, PoolModel, PoolAccount)
            .join(PoolModel, Pool.id == PoolModel.pool_id)
            .join(PoolAccount, Pool.id == PoolAccount.pool_id)
            .where(
                Pool.is_enabled.is_(True),
                PoolModel.is_enabled.is_(True),
                PoolModel.model_slug.in_(model_slugs),
                PoolAccount.status == PoolAccountStatus.ACTIVE,
            )
            .order_by(Pool.priority.desc(), PoolAccount.weight.desc())
        )
        return list(rows.all())

    async def get_available_model_slugs(self) -> list[tuple[str, str]]:
        """Return (model_slug, pool_name) pairs for models with active routing coverage."""
        stmt = (
            select(PoolModel.model_slug, Pool.name)
            .join(Pool, Pool.id == PoolModel.pool_id)
            .join(PoolAccount, Pool.id == PoolAccount.pool_id)
            .where(
                Pool.is_enabled.is_(True),
                PoolModel.is_enabled.is_(True),
                PoolAccount.status == PoolAccountStatus.ACTIVE,
            )
            .group_by(PoolModel.model_slug, Pool.id, Pool.name)
            .order_by(PoolModel.model_slug, Pool.priority.desc())
        )
        rows = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in rows.all()]


class PoolModelRepository(BaseRepository[PoolModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PoolModel)

    async def get_by_pool_and_model(
        self, pool_id: int, model_slug: str,
    ) -> PoolModel | None:
        return (
            await self.session.execute(
                select(PoolModel).where(
                    PoolModel.pool_id == pool_id,
                    PoolModel.model_slug == model_slug,
                )
            )
        ).scalar_one_or_none()

    async def remove(self, pool_id: int, model_slug: str) -> bool:
        result = await self.session.execute(
            delete(PoolModel).where(
                PoolModel.pool_id == pool_id,
                PoolModel.model_slug == model_slug,
            )
        )
        return result.rowcount > 0


class PoolAccountRepository(BaseRepository[PoolAccount]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PoolAccount)

    async def get_by_id_and_pool(
        self, account_id: int, pool_id: int,
    ) -> PoolAccount | None:
        return (
            await self.session.execute(
                select(PoolAccount).where(
                    PoolAccount.id == account_id,
                    PoolAccount.pool_id == pool_id,
                )
            )
        ).scalar_one_or_none()
