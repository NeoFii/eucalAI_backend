"""Call log repository — route monitor queries for admin dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.models import ApiCallLog, User


# Rows tagged with this error_code came from requests that used a model name
# outside the admin-configured allowlist. Excluded from aggregations.
_INVALID_MODEL_ERROR_CODE = "invalid_model"


def _exclude_invalid_model():
    """Build a boolean clause that filters out invalid_model rows."""
    return or_(
        ApiCallLog.error_code.is_(None),
        ApiCallLog.error_code != _INVALID_MODEL_ERROR_CODE,
    )


def _percentile(sorted_samples: list[int], n: int, p: float) -> int:
    """Pick the p-th percentile from a pre-sorted list (1-based ceiling rank)."""
    idx = max(0, min(n - 1, int(round(p * n)) - 1))
    return sorted_samples[idx]


class CallLogRepository:
    """Read-only queries that back the admin route-monitor panel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- List ----------

    async def list_requests(
        self,
        *,
        params: ListParams,
        user_id: int | None = None,
        model_name: str | None = None,
        selected_model: str | None = None,
        provider_slug: str | None = None,
        routing_tier: int | None = None,
        status: int | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        request_id: str | None = None,
        input_hash: str | None = None,
    ) -> PaginatedResult[ApiCallLog]:
        """Paginated drill-down list with dynamic user_uid attribute."""
        query = select(ApiCallLog, User.uid).join(
            User, ApiCallLog.user_id == User.id, isouter=True
        )
        if request_id is not None:
            query = query.where(ApiCallLog.request_id == request_id)
        if user_id is not None:
            query = query.where(ApiCallLog.user_id == user_id)
        if model_name is not None:
            query = query.where(ApiCallLog.model_name == model_name)
        if selected_model is not None:
            query = query.where(ApiCallLog.selected_model == selected_model)
        if provider_slug is not None:
            query = query.where(ApiCallLog.provider_slug == provider_slug)
        if routing_tier is not None:
            query = query.where(ApiCallLog.routing_tier == routing_tier)
        if status is not None:
            query = query.where(ApiCallLog.status == status)
        if score_min is not None:
            query = query.where(ApiCallLog.total_score_0_10 >= score_min)
        if score_max is not None:
            query = query.where(ApiCallLog.total_score_0_10 <= score_max)
        if input_hash is not None:
            query = query.where(ApiCallLog.input_hash == input_hash)

        if params.time_field is not None:
            start, end = params.validate_time_range()
            time_column = getattr(ApiCallLog, params.time_field)
            query = query.where(time_column >= start, time_column < end)

        order_by = params.order_by or "created_at"
        order_column = getattr(ApiCallLog, order_by)
        query = query.order_by(
            order_column.asc() if params.order_dir == "asc" else order_column.desc()
        )
        total = int(
            (await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar()
            or 0
        )
        rows = (
            await self.session.execute(
                query.offset((params.page - 1) * params.page_size).limit(params.page_size)
            )
        ).all()
        items: list[ApiCallLog] = []
        for log, uid in rows:
            log.user_uid = uid
            items.append(log)
        return PaginatedResult(
            items=items, total=total, page=params.page, page_size=params.page_size
        )

    # ---------- Detail ----------

    async def get_request_detail(self, request_id: str) -> ApiCallLog | None:
        """Fetch a single row with dynamic user_uid attribute."""
        row = (
            await self.session.execute(
                select(ApiCallLog, User.uid)
                .join(User, ApiCallLog.user_id == User.id, isouter=True)
                .where(ApiCallLog.request_id == request_id)
            )
        ).one_or_none()
        if row is None:
            return None
        log, uid = row
        log.user_uid = uid
        return log

    # ---------- Compare/Replay ----------

    async def find_same_input_siblings(
        self,
        *,
        request_id: str,
        limit: int = 20,
    ) -> tuple[ApiCallLog | None, list[ApiCallLog]]:
        """Return (target_row, siblings_with_same_input_hash)."""
        target_row = (
            await self.session.execute(
                select(ApiCallLog, User.uid)
                .join(User, ApiCallLog.user_id == User.id, isouter=True)
                .where(ApiCallLog.request_id == request_id)
            )
        ).one_or_none()
        if target_row is None:
            return None, []
        target, target_uid = target_row
        target.user_uid = target_uid
        if not target.input_hash:
            return target, []
        sibling_rows = (
            await self.session.execute(
                select(ApiCallLog, User.uid)
                .join(User, ApiCallLog.user_id == User.id, isouter=True)
                .where(
                    ApiCallLog.input_hash == target.input_hash,
                    ApiCallLog.request_id != request_id,
                )
                .order_by(ApiCallLog.created_at.desc())
                .limit(limit)
            )
        ).all()
        siblings: list[ApiCallLog] = []
        for log, uid in sibling_rows:
            log.user_uid = uid
            siblings.append(log)
        return target, siblings

    # PLACEHOLDER_CALLLOG_CONTINUE

    # ---------- Aggregate Dashboard ----------

    async def aggregate_metrics(
        self,
        *,
        start: datetime,
        end: datetime,
        user_id: int | None = None,
        model_name: str | None = None,
        provider_slug: str | None = None,
    ) -> dict[str, Any]:
        """Compute aggregate buckets for the dashboard view."""
        base_filters = [
            ApiCallLog.created_at >= start,
            ApiCallLog.created_at < end,
        ]
        if user_id is not None:
            base_filters.append(ApiCallLog.user_id == user_id)
        if model_name is not None:
            base_filters.append(ApiCallLog.model_name == model_name)
        if provider_slug is not None:
            base_filters.append(ApiCallLog.provider_slug == provider_slug)

        chart_filters = [*base_filters, _exclude_invalid_model()]

        # 1. totals
        totals_q = select(
            func.count().label("cnt"),
            func.sum(case((ApiCallLog.status == 200, 1), else_=0)).label("ok"),
            func.sum(case(
                (and_(ApiCallLog.status.isnot(None), ApiCallLog.status != 200), 1),
                else_=0,
            )).label("err"),
        ).where(*base_filters)
        totals_row = (await self.session.execute(totals_q)).one()

        # 2. time-series
        range_seconds = int((end - start).total_seconds())
        if range_seconds <= 1800:
            bucket_seconds = 60
        elif range_seconds <= 3600:
            bucket_seconds = 300
        elif range_seconds <= 21600:
            bucket_seconds = 900
        elif range_seconds <= 86400:
            bucket_seconds = 1800
        elif range_seconds <= 259200:
            bucket_seconds = 3600
        else:
            bucket_seconds = 86400

        bucket_expr = func.floor(
            func.unix_timestamp(ApiCallLog.created_at) / bucket_seconds
        ).label("bucket")
        ts_q = (
            select(
                bucket_expr,
                func.count().label("cnt"),
                func.sum(case((ApiCallLog.status == 200, 1), else_=0)).label("ok"),
                func.sum(case(
                    (and_(ApiCallLog.status.isnot(None), ApiCallLog.status != 200), 1),
                    else_=0,
                )).label("err"),
            )
            .where(*base_filters)
            .group_by(bucket_expr)
            .order_by(bucket_expr.asc())
        )
        ts_rows = (await self.session.execute(ts_q)).all()

        # 3. by selected_model (top 20)
        model_q = (
            select(
                ApiCallLog.selected_model.label("model"),
                func.count().label("cnt"),
            )
            .where(*chart_filters, ApiCallLog.selected_model.is_not(None))
            .group_by(ApiCallLog.selected_model)
            .order_by(func.count().desc())
            .limit(20)
        )
        model_rows = (await self.session.execute(model_q)).all()

        # 4. by score bucket
        score_floor = func.floor(ApiCallLog.total_score_0_10).label("floor")
        score_q = (
            select(score_floor, func.count().label("cnt"))
            .where(*chart_filters, ApiCallLog.total_score_0_10.is_not(None))
            .group_by(score_floor)
            .order_by(score_floor.asc())
        )
        score_rows = (await self.session.execute(score_q)).all()

        # 5. provider latency percentiles
        latency_q = select(
            ApiCallLog.provider_slug,
            ApiCallLog.upstream_latency_ms,
        ).where(
            *chart_filters,
            ApiCallLog.provider_slug.is_not(None),
            ApiCallLog.upstream_latency_ms.is_not(None),
        )
        latency_rows = (await self.session.execute(latency_q)).all()
        latencies_by_provider: dict[str, list[int]] = {}
        for row in latency_rows:
            latencies_by_provider.setdefault(row.provider_slug, []).append(
                int(row.upstream_latency_ms)
            )

        provider_latencies = []
        for provider, samples in latencies_by_provider.items():
            samples.sort()
            n = len(samples)
            if n == 0:
                continue
            provider_latencies.append({
                "provider_slug": provider,
                "count": n,
                "p50_ms": _percentile(samples, n, 0.50),
                "p95_ms": _percentile(samples, n, 0.95),
                "p99_ms": _percentile(samples, n, 0.99),
            })
        provider_latencies.sort(key=lambda x: x["count"], reverse=True)

        return {
            "range_start": start,
            "range_end": end,
            "total": int(totals_row.cnt or 0),
            "success_total": int(totals_row.ok or 0),
            "error_total": int(totals_row.err or 0),
            "by_time": [
                {
                    "timestamp": int(r.bucket * bucket_seconds),
                    "total": int(r.cnt or 0),
                    "success": int(r.ok or 0),
                    "error": int(r.err or 0),
                }
                for r in ts_rows
            ],
            "by_model": [
                {"selected_model": str(r.model), "count": int(r.cnt or 0)}
                for r in model_rows
            ],
            "by_score": [
                {
                    "floor": min(9, int(r.floor or 0)),
                    "count": int(r.cnt or 0),
                }
                for r in score_rows
            ],
            "by_provider_latency": provider_latencies,
        }
