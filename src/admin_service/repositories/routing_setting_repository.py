"""Repository for routing_settings table."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.models.routing_setting import RoutingSetting


class RoutingSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[RoutingSetting]:
        rows = await self.session.execute(
            select(RoutingSetting).order_by(RoutingSetting.group_name, RoutingSetting.sort_order)
        )
        return list(rows.scalars().all())

    async def get_by_key(self, key: str) -> RoutingSetting | None:
        return (
            await self.session.execute(
                select(RoutingSetting).where(RoutingSetting.key == key)
            )
        ).scalar_one_or_none()

    async def get_by_group(self, group_name: str) -> list[RoutingSetting]:
        rows = await self.session.execute(
            select(RoutingSetting)
            .where(RoutingSetting.group_name == group_name)
            .order_by(RoutingSetting.sort_order)
        )
        return list(rows.scalars().all())

    async def update_value(self, key: str, value: str, updated_by: int | None = None) -> None:
        await self.session.execute(
            update(RoutingSetting)
            .where(RoutingSetting.key == key)
            .values(value=value, updated_by=updated_by)
        )

    async def batch_update(self, items: Sequence[tuple[str, str]], updated_by: int | None = None) -> None:
        for key, value in items:
            await self.session.execute(
                update(RoutingSetting)
                .where(RoutingSetting.key == key)
                .values(value=value, updated_by=updated_by)
            )
