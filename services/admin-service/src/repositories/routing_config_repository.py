"""Repositories for routing configuration and provider credentials."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.routing_config import ProviderCredential, RoutingConfig
from common.db.query import ListParams
from common.db.repository import BaseRepository

_logger = logging.getLogger(__name__)
_MAX_VERSION_RETRIES = 3


class RoutingConfigRepository(BaseRepository[RoutingConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RoutingConfig)

    async def create_with_version_retry(self, config: RoutingConfig) -> RoutingConfig:
        for attempt in range(_MAX_VERSION_RETRIES):
            max_version = (
                await self.session.execute(select(func.max(RoutingConfig.version)))
            ).scalar()
            config.version = (max_version or 0) + 1
            try:
                async with self.session.begin_nested():
                    self.session.add(config)
                    await self.session.flush()
                return config
            except IntegrityError:
                if attempt == _MAX_VERSION_RETRIES - 1:
                    raise
                _logger.warning("version %d conflict, retrying (%d)", config.version, attempt + 1)
                self.session.expunge(config)
        raise RuntimeError("unreachable")

    async def get_by_version(self, version: int) -> RoutingConfig | None:
        return (
            await self.session.execute(
                select(RoutingConfig).where(RoutingConfig.version == version)
            )
        ).scalar_one_or_none()

    async def get_active(self) -> RoutingConfig | None:
        return (
            await self.session.execute(
                select(RoutingConfig).where(RoutingConfig.status == "active")
            )
        ).scalar_one_or_none()

    async def list_versions(
        self, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[RoutingConfig], int]:
        result = await self.get_list(
            ListParams(page=page, page_size=page_size, order_by="version", order_dir="desc"),
        )
        return list(result.items), result.total

    async def publish(self, config: RoutingConfig, published_by: int) -> None:
        await self.session.execute(
            update(RoutingConfig)
            .where(RoutingConfig.status == "active")
            .values(status="superseded")
        )
        from common.utils.timezone import now

        config.status = "active"
        config.published_at = now()
        config.published_by = published_by
        await self.session.flush()


class ProviderCredentialRepository(BaseRepository[ProviderCredential]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProviderCredential)

    async def get_by_slug(self, slug: str) -> ProviderCredential | None:
        return (
            await self.session.execute(
                select(ProviderCredential).where(ProviderCredential.slug == slug)
            )
        ).scalar_one_or_none()

    async def get_active_by_slug(self, slug: str) -> ProviderCredential | None:
        return (
            await self.session.execute(
                select(ProviderCredential).where(
                    ProviderCredential.slug == slug,
                    ProviderCredential.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self, *, page: int = 1, page_size: int = 50
    ) -> tuple[list[ProviderCredential], int]:
        result = await self.get_list(
            ListParams(page=page, page_size=page_size, order_by="created_at", order_dir="desc"),
        )
        return list(result.items), result.total

    async def get_active_by_slugs(self, slugs: Sequence[str]) -> dict[str, ProviderCredential]:
        if not slugs:
            return {}
        rows = await self.session.execute(
            select(ProviderCredential).where(
                ProviderCredential.slug.in_(slugs),
                ProviderCredential.is_active.is_(True),
            )
        )
        return {cred.slug: cred for cred in rows.scalars().all()}
