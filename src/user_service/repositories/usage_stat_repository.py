"""Usage stat repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from common.db import BaseRepository
from user_service.models import ApiCallLog, UsageStat


class UsageStatRepository(BaseRepository[UsageStat]):
    def __init__(self, session) -> None:
        super().__init__(session, UsageStat)

    async def get_user_stats(
        self,
        *,
        user_id: int,
        start: datetime,
        end: datetime,
        model_name: str | None,
        api_key_id: int | None,
    ) -> list[UsageStat]:
        query = select(UsageStat).where(
            UsageStat.user_id == user_id,
            UsageStat.stat_hour >= start,
            UsageStat.stat_hour < end,
        )
        if model_name is not None:
            query = query.where(UsageStat.model_name == model_name)
        query = query.where(
            UsageStat.api_key_id.is_(None) if api_key_id is None else UsageStat.api_key_id == api_key_id
        )
        query = query.order_by(UsageStat.stat_hour.desc(), UsageStat.model_name.asc())
        return list((await self.session.execute(query)).scalars().all())

    async def get_all_stats(
        self,
        *,
        start: datetime,
        end: datetime,
        user_id: int | None,
        model_name: str | None,
    ) -> list[UsageStat]:
        query = select(UsageStat).where(
            UsageStat.stat_hour >= start,
            UsageStat.stat_hour < end,
            UsageStat.api_key_id.is_(None),
        )
        if user_id is not None:
            query = query.where(UsageStat.user_id == user_id)
        if model_name is not None:
            query = query.where(UsageStat.model_name == model_name)
        query = query.order_by(UsageStat.stat_hour.desc(), UsageStat.user_id.asc(), UsageStat.model_name.asc())
        return list((await self.session.execute(query)).scalars().all())

    async def list_usage_logs(
        self,
        *,
        user_id: int | None,
        start: datetime | None,
        end: datetime | None,
        api_key_id: int | None,
        model_name: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ApiCallLog], int]:
        query = select(ApiCallLog)
        if user_id is not None:
            query = query.where(ApiCallLog.user_id == user_id)
        if api_key_id is not None:
            query = query.where(ApiCallLog.api_key_id == api_key_id)
        if model_name is not None:
            query = query.where(ApiCallLog.model_name == model_name)
        if start is not None:
            query = query.where(ApiCallLog.created_at >= start)
        if end is not None:
            query = query.where(ApiCallLog.created_at < end)
        query = query.order_by(ApiCallLog.created_at.desc())
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total
