"""Repositories for pools, pool_models, and pool_accounts."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin_service.models.pool import Pool, PoolAccount, PoolModel
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
        count_stmt = select(func.count(Pool.id))
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        stmt = (
            select(Pool)
            .options(selectinload(Pool.models), selectinload(Pool.accounts))
            .order_by(Pool.priority.desc(), Pool.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().unique().all()), total

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
                PoolAccount.status == "active",
            )
            .order_by(Pool.priority.desc(), PoolAccount.weight.desc())
        )
        return list(rows.all())


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
