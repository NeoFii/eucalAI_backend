"""Usage stat repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, cast, func, select, Date

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

    async def get_daily_platform_stats(
        self, *, start: datetime, end: datetime,
    ) -> list[dict]:
        stat_date = cast(ApiCallLog.created_at, Date).label("stat_date")
        query = (
            select(
                stat_date,
                func.count().label("request_count"),
                func.sum(case((ApiCallLog.status == 1, 1), else_=0)).label("success_count"),
                func.sum(case((ApiCallLog.status == 2, 1), else_=0)).label("error_count"),
                func.sum(ApiCallLog.prompt_tokens).label("prompt_tokens"),
                func.sum(ApiCallLog.completion_tokens).label("completion_tokens"),
                func.sum(ApiCallLog.cached_tokens).label("cached_tokens"),
                func.sum(ApiCallLog.total_tokens).label("total_tokens"),
                func.sum(ApiCallLog.cost).label("total_revenue"),
                func.sum(ApiCallLog.provider_cost).label("total_provider_cost"),
            )
            .where(ApiCallLog.created_at >= start, ApiCallLog.created_at < end)
            .group_by(stat_date)
            .order_by(stat_date.asc())
        )
        rows = (await self.session.execute(query)).all()
        return [
            {
                "date": str(r.stat_date),
                "request_count": int(r.request_count or 0),
                "success_count": int(r.success_count or 0),
                "error_count": int(r.error_count or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "cached_tokens": int(r.cached_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_revenue": int(r.total_revenue or 0),
                "total_provider_cost": int(r.total_provider_cost or 0),
            }
            for r in rows
        ]

    async def get_model_call_stats(
        self, *, start: datetime, end: datetime,
    ) -> list[dict]:
        effective_model = func.coalesce(
            ApiCallLog.selected_model, ApiCallLog.model_name,
        ).label("model")
        query = (
            select(
                effective_model,
                func.count().label("request_count"),
                func.sum(ApiCallLog.cost).label("total_revenue"),
                func.sum(ApiCallLog.provider_cost).label("total_provider_cost"),
                func.sum(ApiCallLog.prompt_tokens).label("prompt_tokens"),
                func.sum(ApiCallLog.completion_tokens).label("completion_tokens"),
            )
            .where(ApiCallLog.created_at >= start, ApiCallLog.created_at < end)
            .group_by(effective_model)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(query)).all()
        return [
            {
                "model": r.model,
                "request_count": int(r.request_count or 0),
                "total_revenue": int(r.total_revenue or 0),
                "total_provider_cost": int(r.total_provider_cost or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in rows
        ]

    async def get_platform_summary(self, *, today_start: datetime) -> dict:
        total_q = select(func.count()).select_from(ApiCallLog)
        total_result = await self.session.execute(total_q)
        total_requests = int(total_result.scalar() or 0)

        today_q = (
            select(
                func.count().label("cnt"),
                func.sum(ApiCallLog.cost).label("rev"),
                func.sum(ApiCallLog.provider_cost).label("cost"),
            )
            .where(ApiCallLog.created_at >= today_start)
        )
        today_row = (await self.session.execute(today_q)).one()

        all_q = select(
            func.sum(ApiCallLog.cost).label("rev"),
            func.sum(ApiCallLog.provider_cost).label("cost"),
        )
        all_row = (await self.session.execute(all_q)).one()

        return {
            "total_requests": total_requests,
            "requests_today": int(today_row.cnt or 0),
            "total_revenue": int(all_row.rev or 0),
            "revenue_today": int(today_row.rev or 0),
            "total_provider_cost": int(all_row.cost or 0),
            "provider_cost_today": int(today_row.cost or 0),
        }
