"""Pool repository — merges pool, pool model config, and pool account access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api_service.common.infra.db.repository import BaseRepository
from api_service.common.infra.db.query import ListParams
from api_service.models import Pool, PoolModelConfig, PoolAccount
from api_service.models.enums import PoolAccountStatus


class PoolRepository(BaseRepository[Pool]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Pool)

    # ──────────────────────────────────────────────
    # Pool methods
    # ──────────────────────────────────────────────

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
        from sqlalchemy import func, asc, desc
        statement = (
            select(Pool)
            .options(selectinload(Pool.models), selectinload(Pool.accounts))
            .order_by(Pool.priority.desc())
        )
        count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        offset = (page - 1) * page_size
        rows = await self.session.execute(statement.offset(offset).limit(page_size))
        return list(rows.scalars().all()), total

    async def get_active_for_routing(
        self, model_slugs: Sequence[str],
    ) -> list[tuple[Pool, PoolModelConfig, PoolAccount]]:
        """Return (pool, pool_model_config, pool_account) triples for active routing."""
        if not model_slugs:
            return []
        rows = await self.session.execute(
            select(Pool, PoolModelConfig, PoolAccount)
            .join(PoolModelConfig, Pool.id == PoolModelConfig.pool_id)
            .join(PoolAccount, Pool.id == PoolAccount.pool_id)
            .where(
                Pool.is_enabled.is_(True),
                PoolModelConfig.is_enabled.is_(True),
                PoolModelConfig.model_slug.in_(model_slugs),
                PoolAccount.status == PoolAccountStatus.ACTIVE,
            )
            .order_by(Pool.priority.desc(), PoolAccount.weight.desc())
        )
        return list(rows.all())

    async def get_available_model_slugs(self) -> list[tuple[str, str]]:
        """Return (model_slug, pool_name) pairs for models with active routing coverage."""
        stmt = (
            select(PoolModelConfig.model_slug, Pool.name)
            .join(Pool, Pool.id == PoolModelConfig.pool_id)
            .join(PoolAccount, Pool.id == PoolAccount.pool_id)
            .where(
                Pool.is_enabled.is_(True),
                PoolModelConfig.is_enabled.is_(True),
                PoolAccount.status == PoolAccountStatus.ACTIVE,
            )
            .group_by(PoolModelConfig.model_slug, Pool.id, Pool.name)
            .order_by(PoolModelConfig.model_slug, Pool.priority.desc())
        )
        rows = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in rows.all()]

    async def get_model_cost(self, model_slug: str) -> list[tuple[str, int, int, int | None]]:
        """Return (pool_name, cost_input, cost_output, cost_cached) for a model_slug."""
        stmt = (
            select(
                Pool.name,
                PoolModelConfig.cost_input_per_million,
                PoolModelConfig.cost_output_per_million,
                PoolModelConfig.cost_cached_input_per_million,
            )
            .join(Pool, Pool.id == PoolModelConfig.pool_id)
            .where(
                PoolModelConfig.model_slug == model_slug,
                PoolModelConfig.is_enabled.is_(True),
                Pool.is_enabled.is_(True),
            )
            .order_by(Pool.priority.desc())
        )
        rows = await self.session.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in rows.all()]

    # ──────────────────────────────────────────────
    # PoolModelConfig methods (prefixed with model_config_)
    # ──────────────────────────────────────────────

    async def model_config_get_by_pool_and_model(
        self, pool_id: int, model_slug: str,
    ) -> PoolModelConfig | None:
        return (
            await self.session.execute(
                select(PoolModelConfig).where(
                    PoolModelConfig.pool_id == pool_id,
                    PoolModelConfig.model_slug == model_slug,
                )
            )
        ).scalar_one_or_none()

    async def model_config_remove(self, pool_id: int, model_slug: str) -> bool:
        result = await self.session.execute(
            delete(PoolModelConfig).where(
                PoolModelConfig.pool_id == pool_id,
                PoolModelConfig.model_slug == model_slug,
            )
        )
        return result.rowcount > 0

    def model_config_add(self, instance: PoolModelConfig) -> None:
        self.session.add(instance)

    # ──────────────────────────────────────────────
    # PoolAccount methods (prefixed with account_)
    # ──────────────────────────────────────────────

    async def account_get_by_id_and_pool(
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

    def account_add(self, instance: PoolAccount) -> None:
        self.session.add(instance)
