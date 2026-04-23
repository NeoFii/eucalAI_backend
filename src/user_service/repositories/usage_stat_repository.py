"""Usage stat repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from common.db import BaseRepository, ListParams, PaginatedResult
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
        params: ListParams,
        user_id: int | None,
        api_key_id: int | None,
        model_name: str | None,
        effective_model: str | None = None,
        request_id: str | None = None,
    ) -> PaginatedResult[ApiCallLog]:
        query = select(ApiCallLog)
        if request_id is not None:
            query = query.where(ApiCallLog.request_id == request_id)
        if user_id is not None:
            query = query.where(ApiCallLog.user_id == user_id)
        if api_key_id is not None:
            query = query.where(ApiCallLog.api_key_id == api_key_id)
        if model_name is not None:
            query = query.where(ApiCallLog.model_name == model_name)
        if effective_model is not None:
            query = query.where(
                func.coalesce(ApiCallLog.selected_model, ApiCallLog.model_name) == effective_model
            )
        if params.time_field is not None:
            start, end = params.validate_time_range()
            time_column = getattr(ApiCallLog, params.time_field)
            query = query.where(time_column >= start, time_column < end)
        order_by = params.order_by or "created_at"
        order_column = getattr(ApiCallLog, order_by)
        query = query.order_by(order_column.asc() if params.order_dir == "asc" else order_column.desc())
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list(
            (
                await self.session.execute(
                    query.offset((params.page - 1) * params.page_size).limit(params.page_size)
                )
            )
            .scalars()
            .all()
        )
        return PaginatedResult(items=items, total=total, page=params.page, page_size=params.page_size)

    async def list_analytics_logs(
        self,
        *,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> list[ApiCallLog]:
        query = (
            select(ApiCallLog)
            .where(
                ApiCallLog.user_id == user_id,
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
            )
            .order_by(ApiCallLog.created_at.asc(), ApiCallLog.id.asc())
        )
        return list((await self.session.execute(query)).scalars().all())

    async def list_logs_for_hour(self, stat_hour: datetime, next_hour: datetime) -> list[ApiCallLog]:
        query = select(ApiCallLog).where(
            ApiCallLog.created_at >= stat_hour,
            ApiCallLog.created_at < next_hour,
        )
        return list((await self.session.execute(query)).scalars().all())

    async def get_bucket(
        self,
        *,
        user_id: int,
        api_key_id: int | None,
        model_name: str,
        stat_hour: datetime,
    ) -> UsageStat | None:
        return (
            await self.session.execute(
                select(UsageStat).where(
                    UsageStat.user_id == user_id,
                    UsageStat.model_name == model_name,
                    UsageStat.stat_hour == stat_hour,
                    UsageStat.api_key_id.is_(None)
                    if api_key_id is None
                    else UsageStat.api_key_id == api_key_id,
                )
            )
        ).scalar_one_or_none()
