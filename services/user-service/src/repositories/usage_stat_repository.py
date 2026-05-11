"""Usage stat repository."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, cast, func, or_, select, Date

from common.db import BaseRepository, ListParams, PaginatedResult
from common.utils.timezone import format_iso, now
from models import ApiCallLog, UsageStat


# Rows tagged with this error_code came from requests that used a model name
# outside the admin-configured allowlist (`routing_settings.user_facing_aliases`).
# We deliberately leave them in `api_call_logs` so the request-detail list still
# shows the offending entry, but exclude them from every aggregation/chart so
# they don't pollute cost-distribution / request-share / ranking views.
_INVALID_MODEL_ERROR_CODE = "invalid_model"


def _exclude_invalid_model():
    """Build a boolean clause that filters out invalid_model rows in api_call_logs."""
    return or_(
        ApiCallLog.error_code.is_(None),
        ApiCallLog.error_code != _INVALID_MODEL_ERROR_CODE,
    )


class UsageStatRepository(BaseRepository[UsageStat]):
    def __init__(self, session) -> None:
        super().__init__(session, UsageStat)

    async def get_user_tpm_last_minute(self, user_id: int) -> int:
        """Sum total_tokens for the user over the last 60 seconds.

        Used to surface a real-time TPM gauge (tokens/min currently being
        consumed) to user / admin UIs. PENDING + SUCCESS rows are both
        counted: PENDING covers in-flight streamed responses that haven't
        finalized yet; ERROR / REFUNDED / ABORTED are excluded because they
        don't represent successful token throughput.
        """
        cutoff = now() - timedelta(seconds=60)
        result = await self.session.execute(
            select(func.coalesce(func.sum(ApiCallLog.total_tokens), 0))
            .where(
                ApiCallLog.user_id == user_id,
                ApiCallLog.created_at >= cutoff,
                ApiCallLog.status.in_([
                    ApiCallLog.STATUS_PENDING,
                    ApiCallLog.STATUS_SUCCESS,
                ]),
            )
        )
        return int(result.scalar() or 0)

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
        api_key_id: int | None = None,
    ) -> list[ApiCallLog]:
        query = (
            select(ApiCallLog)
            .where(
                ApiCallLog.user_id == user_id,
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
                _exclude_invalid_model(),
            )
            .order_by(ApiCallLog.created_at.asc(), ApiCallLog.id.asc())
        )
        if api_key_id is not None:
            query = query.where(ApiCallLog.api_key_id == api_key_id)
        return list((await self.session.execute(query)).scalars().all())

    async def list_logs_for_hour(self, stat_hour: datetime, next_hour: datetime) -> list[ApiCallLog]:
        query = select(ApiCallLog).where(
            ApiCallLog.created_at >= stat_hour,
            ApiCallLog.created_at < next_hour,
            _exclude_invalid_model(),
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
            .where(
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
                _exclude_invalid_model(),
            )
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
            .where(
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
                _exclude_invalid_model(),
            )
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

    async def get_platform_summary(
        self,
        *,
        today_start: datetime,
        range_start: datetime | None = None,
        range_end: datetime | None = None,
    ) -> dict:
        total_q = (
            select(func.count())
            .select_from(ApiCallLog)
            .where(_exclude_invalid_model())
        )
        total_result = await self.session.execute(total_q)
        total_requests = int(total_result.scalar() or 0)

        today_q = (
            select(
                func.count().label("cnt"),
                func.sum(ApiCallLog.cost).label("rev"),
                func.sum(ApiCallLog.provider_cost).label("cost"),
            )
            .where(
                ApiCallLog.created_at >= today_start,
                _exclude_invalid_model(),
            )
        )
        today_row = (await self.session.execute(today_q)).one()

        all_q = (
            select(
                func.sum(ApiCallLog.cost).label("rev"),
                func.sum(ApiCallLog.provider_cost).label("cost"),
            )
            .where(_exclude_invalid_model())
        )
        all_row = (await self.session.execute(all_q)).one()

        # 区间统计（区间未指定时退化为今日的值）
        if range_start is not None or range_end is not None:
            range_filters = [_exclude_invalid_model()]
            if range_start is not None:
                range_filters.append(ApiCallLog.created_at >= range_start)
            if range_end is not None:
                range_filters.append(ApiCallLog.created_at < range_end)
            range_q = (
                select(
                    func.count().label("cnt"),
                    func.sum(ApiCallLog.cost).label("rev"),
                    func.sum(ApiCallLog.provider_cost).label("cost"),
                )
                .where(*range_filters)
            )
            range_row = (await self.session.execute(range_q)).one()
            requests_in_range = int(range_row.cnt or 0)
            revenue_in_range = int(range_row.rev or 0)
            provider_cost_in_range = int(range_row.cost or 0)
        else:
            requests_in_range = int(today_row.cnt or 0)
            revenue_in_range = int(today_row.rev or 0)
            provider_cost_in_range = int(today_row.cost or 0)

        return {
            "total_requests": total_requests,
            "requests_today": int(today_row.cnt or 0),
            "total_revenue": int(all_row.rev or 0),
            "revenue_today": int(today_row.rev or 0),
            "total_provider_cost": int(all_row.cost or 0),
            "provider_cost_today": int(today_row.cost or 0),
            "requests_in_range": requests_in_range,
            "revenue_in_range": revenue_in_range,
            "provider_cost_in_range": provider_cost_in_range,
        }

    async def get_rpm_trend(
        self,
        *,
        start: datetime,
        end: datetime,
        bucket_seconds: int,
    ) -> list[dict]:
        """Aggregate api_call_logs request counts into fixed-width time buckets.

        Used to render the platform RPM trend chart. Buckets that contain no
        rows are filled with 0 by the caller / Python side to keep the time
        axis continuous (this method only returns buckets with > 0 rows).

        Excludes ``error_code='invalid_model'`` rows for parity with other
        chart-facing aggregations (cost / request-share / ranking views).
        """
        # MySQL: align created_at to bucket boundary using
        #   FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(t) / N) * N)
        bucket_expr = func.from_unixtime(
            func.floor(func.unix_timestamp(ApiCallLog.created_at) / bucket_seconds)
            * bucket_seconds
        ).label("bucket_start")

        query = (
            select(
                bucket_expr,
                func.count().label("request_count"),
            )
            .where(
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
                _exclude_invalid_model(),
            )
            .group_by(bucket_expr)
            .order_by(bucket_expr.asc())
        )
        rows = (await self.session.execute(query)).all()

        bucket_minutes = bucket_seconds / 60.0
        return [
            {
                "bucket_start": format_iso(r.bucket_start),
                "request_count": int(r.request_count or 0),
                "rpm": round((r.request_count or 0) / bucket_minutes, 3),
            }
            for r in rows
        ]
