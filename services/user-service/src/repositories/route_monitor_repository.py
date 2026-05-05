"""Route-monitor repository: paginated drill-down + aggregates + compare/replay queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams, PaginatedResult
from models import ApiCallLog, User
from repositories.usage_stat_repository import _exclude_invalid_model


def _percentile(sorted_samples: list[int], n: int, p: float) -> int:
    """Pick the p-th percentile from a pre-sorted list (1-based ceiling rank)."""
    idx = max(0, min(n - 1, int(round(p * n)) - 1))
    return sorted_samples[idx]


class RouteMonitorRepository:
    """Read-only queries that back the admin route-monitor panel.

    All aggregate queries exclude rows tagged `error_code='invalid_model'` for
    consistency with the other admin charts (those are user-input typos and
    would otherwise dominate the by-tier=NULL bucket).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- 列表 ----------

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
        """Paginated drill-down list.

        Note: SQLAlchemy `select(ApiCallLog)` loads all columns including the
        big `request_preview` JSON. Callers should serialize the rows via
        `RouteRequestListItem` (which omits `request_preview`) so the wire
        payload stays small.

        Each returned `ApiCallLog` row has a dynamically-attached `user_uid`
        attribute (the public NanoID from `users.uid`); the join is an outer
        join so legacy/orphaned rows still surface (uid will be `None`).
        """
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
            log.user_uid = uid  # dynamic attribute consumed by RouteRequestListItem
            items.append(log)
        return PaginatedResult(
            items=items, total=total, page=params.page, page_size=params.page_size
        )

    # ---------- 详情 ----------

    async def get_request_detail(self, request_id: str) -> ApiCallLog | None:
        """Fetch a single row including the full request_preview JSON.

        The returned row has a dynamically-attached `user_uid` attribute
        (the public NanoID from `users.uid`); outer-join so missing user
        records still yield the log row with `user_uid = None`.
        """
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

    # ---------- 对比/回放 ----------

    async def find_same_input_siblings(
        self,
        *,
        request_id: str,
        limit: int = 20,
    ) -> tuple[ApiCallLog | None, list[ApiCallLog]]:
        """Return (target_row, siblings_with_same_input_hash).

        Siblings are ordered most-recent first and exclude the target row.
        If the target has no input_hash (legacy/old rows), siblings is empty.

        Both target and sibling rows have a dynamically-attached `user_uid`
        attribute (outer-joined from users.uid).
        """
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

    # ---------- 聚合仪表盘 ----------

    async def aggregate_metrics(
        self,
        *,
        start: datetime,
        end: datetime,
        user_id: int | None = None,
        model_name: str | None = None,
        provider_slug: str | None = None,
    ) -> dict[str, Any]:
        """Compute the aggregate buckets for the dashboard view.

        Performs 5 queries:
          1. totals (count + success + error)
          2. by routing_tier (count + success + error per tier)
          3. by selected_model (top 20 by count)
          4. by score bucket (0-1, 1-2, ..., 9-10)
          5. by provider: pull (provider_slug, upstream_latency_ms) rows and
             compute p50/p95/p99 in Python; bounded by the time-range filter so
             N stays manageable.
        """
        common_filters = [
            ApiCallLog.created_at >= start,
            ApiCallLog.created_at < end,
            _exclude_invalid_model(),
        ]
        if user_id is not None:
            common_filters.append(ApiCallLog.user_id == user_id)
        if model_name is not None:
            common_filters.append(ApiCallLog.model_name == model_name)
        if provider_slug is not None:
            common_filters.append(ApiCallLog.provider_slug == provider_slug)

        # 1. totals
        totals_q = select(
            func.count().label("cnt"),
            func.sum(case((ApiCallLog.status == 1, 1), else_=0)).label("ok"),
            func.sum(case((ApiCallLog.status == 2, 1), else_=0)).label("err"),
        ).where(*common_filters)
        totals_row = (await self.session.execute(totals_q)).one()

        # 2. by tier
        tier_q = (
            select(
                ApiCallLog.routing_tier.label("tier"),
                func.count().label("cnt"),
                func.sum(case((ApiCallLog.status == 1, 1), else_=0)).label("ok"),
                func.sum(case((ApiCallLog.status == 2, 1), else_=0)).label("err"),
            )
            .where(*common_filters, ApiCallLog.routing_tier.is_not(None))
            .group_by(ApiCallLog.routing_tier)
            .order_by(ApiCallLog.routing_tier.asc())
        )
        tier_rows = (await self.session.execute(tier_q)).all()

        # 3. by selected_model (top 20)
        model_q = (
            select(
                ApiCallLog.selected_model.label("model"),
                func.count().label("cnt"),
            )
            .where(*common_filters, ApiCallLog.selected_model.is_not(None))
            .group_by(ApiCallLog.selected_model)
            .order_by(func.count().desc())
            .limit(20)
        )
        model_rows = (await self.session.execute(model_q)).all()

        # 4. by score bucket (FLOOR(total_score_0_10) → 0..10, clamp 10→9)
        score_floor = func.floor(ApiCallLog.total_score_0_10).label("floor")
        score_q = (
            select(
                score_floor,
                func.count().label("cnt"),
            )
            .where(*common_filters, ApiCallLog.total_score_0_10.is_not(None))
            .group_by(score_floor)
            .order_by(score_floor.asc())
        )
        score_rows = (await self.session.execute(score_q)).all()

        # 5. provider latency: pull rows, compute percentiles in Python
        latency_q = select(
            ApiCallLog.provider_slug,
            ApiCallLog.upstream_latency_ms,
        ).where(
            *common_filters,
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
            "by_tier": [
                {
                    "routing_tier": int(r.tier),
                    "count": int(r.cnt or 0),
                    "success_count": int(r.ok or 0),
                    "error_count": int(r.err or 0),
                }
                for r in tier_rows
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
