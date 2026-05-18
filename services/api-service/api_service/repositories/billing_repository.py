"""Billing repository — merges balance transactions, topup orders, and usage stats."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, cast, func, or_, select, Date
from sqlalchemy.orm import selectinload

from api_service.common.infra.db.repository import BaseRepository
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.common.utils.timezone import format_iso, now
from api_service.models import BalanceTransaction, TopupOrder, UsageStat, ApiCallLog


# Rows tagged with this error_code came from requests that used a model name
# outside the admin-configured allowlist. We exclude them from aggregations.
_INVALID_MODEL_ERROR_CODE = "invalid_model"


def _exclude_invalid_model():
    """Build a boolean clause that filters out invalid_model rows in api_call_logs."""
    return or_(
        ApiCallLog.error_code.is_(None),
        ApiCallLog.error_code != _INVALID_MODEL_ERROR_CODE,
    )


class BillingRepository(BaseRepository[BalanceTransaction]):
    def __init__(self, session) -> None:
        super().__init__(session, BalanceTransaction)

    # ──────────────────────────────────────────────
    # BalanceTransaction methods
    # ──────────────────────────────────────────────

    def add_tx(self, tx: BalanceTransaction) -> None:
        self.session.add(tx)

    async def exists_by_ref(self, *, tx_type: int, ref_type: str, ref_id: str) -> bool:
        existing = (
            await self.session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.type == tx_type,
                    BalanceTransaction.ref_type == ref_type,
                    BalanceTransaction.ref_id == ref_id,
                )
            )
        ).scalar_one_or_none()
        return isinstance(existing, BalanceTransaction)

    async def list_tx_for_user(
        self,
        *,
        user_id: int,
        params: ListParams,
        tx_type: int | None = None,
    ) -> PaginatedResult[BalanceTransaction]:
        if params.order_by is None:
            params.order_by = "created_at"
        filters = [BalanceTransaction.user_id == user_id]
        if tx_type is not None:
            filters.append(BalanceTransaction.type == tx_type)
        return await self.get_list(params, extra_filters=filters)

    async def list_tx_all(
        self,
        *,
        user_id: int | None,
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        if params.order_by is None:
            params.order_by = "created_at"
        filters = ()
        if user_id is not None:
            filters = (BalanceTransaction.user_id == user_id,)
        return await self.get_list(params, extra_filters=filters)

    # ──────────────────────────────────────────────
    # TopupOrder methods (prefixed with topup_)
    # ──────────────────────────────────────────────

    def topup_add(self, order: TopupOrder) -> None:
        self.session.add(order)

    async def topup_get_for_user_by_order_no(
        self,
        *,
        order_no: str,
        user_id: int,
        for_update: bool = False,
    ) -> TopupOrder | None:
        statement = select(TopupOrder).where(
            TopupOrder.order_no == order_no,
            TopupOrder.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def topup_list_for_user(self, *, user_id: int, params: ListParams) -> PaginatedResult[TopupOrder]:
        if params.order_by is None:
            params.order_by = "created_at"
        stmt = select(TopupOrder).where(TopupOrder.user_id == user_id)
        if params.order_by:
            from sqlalchemy import asc, desc
            order_column = getattr(TopupOrder, params.order_by)
            order_fn = asc if params.order_dir.lower() == "asc" else desc
            stmt = stmt.order_by(order_fn(order_column))
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        offset = (params.page - 1) * params.page_size
        rows = await self.session.execute(stmt.offset(offset).limit(params.page_size))
        return PaginatedResult(items=list(rows.scalars().all()), total=total, page=params.page, page_size=params.page_size)

    async def topup_list_all(
        self,
        *,
        params: ListParams,
        user_id: int | None,
        status: int | None,
    ) -> PaginatedResult[TopupOrder]:
        from sqlalchemy import asc, desc
        filters = []
        if user_id is not None:
            filters.append(TopupOrder.user_id == user_id)
        if status is not None:
            filters.append(TopupOrder.status == status)
        if params.order_by is None:
            params.order_by = "created_at"
        stmt = select(TopupOrder)
        if filters:
            stmt = stmt.where(*filters)
        order_column = getattr(TopupOrder, params.order_by)
        order_fn = asc if params.order_dir.lower() == "asc" else desc
        stmt = stmt.order_by(order_fn(order_column))
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        offset = (params.page - 1) * params.page_size
        rows = await self.session.execute(stmt.offset(offset).limit(params.page_size))
        return PaginatedResult(items=list(rows.scalars().all()), total=total, page=params.page, page_size=params.page_size)

    # ──────────────────────────────────────────────
    # UsageStat methods (prefixed with stat_)
    # ──────────────────────────────────────────────

    async def stat_get_user_tpm_last_minute(self, user_id: int) -> int:
        cutoff = now() - timedelta(seconds=60)
        result = await self.session.execute(
            select(func.coalesce(func.sum(ApiCallLog.total_tokens), 0))
            .where(
                ApiCallLog.user_id == user_id,
                ApiCallLog.created_at >= cutoff,
                ApiCallLog.status == 200,
            )
        )
        return int(result.scalar() or 0)

    async def stat_get_user_stats(
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

    # PLACEHOLDER_BILLING_CONTINUE

    async def stat_get_all_stats(
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

    async def stat_list_usage_logs(
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
                    query.options(selectinload(ApiCallLog.api_key))
                    .offset((params.page - 1) * params.page_size)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .all()
        )
        return PaginatedResult(items=items, total=total, page=params.page, page_size=params.page_size)

    # PLACEHOLDER_BILLING_CONTINUE_2

    async def stat_list_analytics_logs(
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

    async def stat_list_logs_for_hour(self, stat_hour: datetime, next_hour: datetime) -> list[ApiCallLog]:
        query = select(ApiCallLog).where(
            ApiCallLog.created_at >= stat_hour,
            ApiCallLog.created_at < next_hour,
            _exclude_invalid_model(),
        )
        return list((await self.session.execute(query)).scalars().all())

    async def stat_get_bucket(
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

    async def stat_get_daily_platform_stats(
        self, *, start: datetime, end: datetime,
    ) -> list[dict]:
        stat_date = cast(ApiCallLog.created_at, Date).label("stat_date")
        query = (
            select(
                stat_date,
                func.count().label("request_count"),
                func.sum(case((ApiCallLog.status == 200, 1), else_=0)).label("success_count"),
                func.sum(case((ApiCallLog.status >= 400, 1), else_=0)).label("error_count"),
                func.sum(case((ApiCallLog.status == 499, 1), else_=0)).label("aborted_count"),
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
                "aborted_count": int(r.aborted_count or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "cached_tokens": int(r.cached_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_revenue": int(r.total_revenue or 0),
                "total_provider_cost": int(r.total_provider_cost or 0),
            }
            for r in rows
        ]

    # PLACEHOLDER_BILLING_CONTINUE_3

    async def stat_get_bucketed_platform_stats(
        self, *, start: datetime, end: datetime, bucket_seconds: int,
    ) -> list[dict]:
        if bucket_seconds >= 86400:
            return await self.stat_get_daily_platform_stats(start=start, end=end)

        bucket_expr = func.from_unixtime(
            func.floor(func.unix_timestamp(ApiCallLog.created_at) / bucket_seconds)
            * bucket_seconds
        ).label("bucket_start")

        query = (
            select(
                bucket_expr,
                func.count().label("request_count"),
                func.sum(case((ApiCallLog.status == 200, 1), else_=0)).label("success_count"),
                func.sum(case((ApiCallLog.status >= 400, 1), else_=0)).label("error_count"),
                func.sum(case((ApiCallLog.status == 499, 1), else_=0)).label("aborted_count"),
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
            .group_by(bucket_expr)
            .order_by(bucket_expr.asc())
        )
        rows = (await self.session.execute(query)).all()
        return [
            {
                "date": format_iso(r.bucket_start),
                "request_count": int(r.request_count or 0),
                "success_count": int(r.success_count or 0),
                "error_count": int(r.error_count or 0),
                "aborted_count": int(r.aborted_count or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "cached_tokens": int(r.cached_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "total_revenue": int(r.total_revenue or 0),
                "total_provider_cost": int(r.total_provider_cost or 0),
            }
            for r in rows
        ]

    async def stat_get_model_call_stats(
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

    # PLACEHOLDER_BILLING_CONTINUE_4

    async def stat_get_platform_summary(
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

    async def stat_get_rpm_trend(
        self,
        *,
        start: datetime,
        end: datetime,
        bucket_seconds: int,
    ) -> list[dict]:
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
                ApiCallLog.status == 200,
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

    async def stat_get_tpm_trend(
        self,
        *,
        start: datetime,
        end: datetime,
        bucket_seconds: int,
    ) -> list[dict]:
        bucket_expr = func.from_unixtime(
            func.floor(func.unix_timestamp(ApiCallLog.created_at) / bucket_seconds)
            * bucket_seconds
        ).label("bucket_start")

        query = (
            select(
                bucket_expr,
                func.coalesce(
                    func.sum(ApiCallLog.prompt_tokens) + func.sum(ApiCallLog.completion_tokens),
                    0,
                ).label("total_tokens"),
            )
            .where(
                ApiCallLog.created_at >= start,
                ApiCallLog.created_at < end,
                ApiCallLog.status == 200,
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
                "total_tokens": int(r.total_tokens or 0),
                "tpm": round(int(r.total_tokens or 0) / bucket_minutes, 3),
            }
            for r in rows
        ]
