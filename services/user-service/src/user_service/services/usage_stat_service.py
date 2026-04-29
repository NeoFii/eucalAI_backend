"""Usage-stat aggregation and query helpers for user-service."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams, PaginatedResult
from common.utils.timezone import now
from user_service.models import ApiCallLog, UsageStat
from user_service.repositories import UsageStatRepository
from user_service.schemas.billing import (
    UsageAnalyticsBucket,
    UsageAnalyticsBucketCost,
    UsageAnalyticsData,
    UsageAnalyticsModel,
    UsageAnalyticsOverview,
    UsageAnalyticsRange,
)


_ANALYTICS_RANGES: dict[UsageAnalyticsRange, tuple[int, str]] = {
    "8h": (8, "hour"),
    "24h": (24, "hour"),
    "7d": (7, "day"),
    "30d": (30, "day"),
}


class UsageStatService:
    """Aggregate api_call_logs into hourly usage buckets."""

    @staticmethod
    async def aggregate_hour(db: AsyncSession, stat_hour: datetime) -> None:
        next_hour = stat_hour + timedelta(hours=1)
        repo = UsageStatRepository(db)
        logs = await repo.list_logs_for_hour(stat_hour, next_hour)

        buckets: dict[tuple[int, int | None, str], dict[str, int]] = defaultdict(
            lambda: {
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0,
            }
        )

        for log in logs:
            UsageStatService._accumulate_bucket(
                buckets[(int(log.user_id), log.api_key_id, log.model_name)],
                log,
            )
            UsageStatService._accumulate_bucket(
                buckets[(int(log.user_id), None, log.model_name)],
                log,
            )

        for (user_id, api_key_id, model_name), metrics in buckets.items():
            existing = await repo.get_bucket(
                user_id=user_id,
                api_key_id=api_key_id,
                model_name=model_name,
                stat_hour=stat_hour,
            )
            if existing is None:
                existing = UsageStat(
                    user_id=user_id,
                    api_key_id=api_key_id,
                    account_api_key_id=api_key_id or 0,
                    model_name=model_name,
                    stat_hour=stat_hour,
                )
                repo.add(existing)
            for field, value in metrics.items():
                setattr(existing, field, value)

        await db.commit()

    @staticmethod
    async def get_user_stats(
        db: AsyncSession,
        user_id: int,
        start: datetime,
        end: datetime,
        model_name: str | None = None,
        api_key_id: int | None = None,
    ) -> list[UsageStat]:
        return await UsageStatRepository(db).get_user_stats(
            user_id=user_id,
            start=start,
            end=end,
            model_name=model_name,
            api_key_id=api_key_id,
        )

    @staticmethod
    async def get_all_stats(
        db: AsyncSession,
        start: datetime,
        end: datetime,
        user_id: int | None = None,
        model_name: str | None = None,
    ) -> list[UsageStat]:
        return await UsageStatRepository(db).get_all_stats(
            start=start,
            end=end,
            user_id=user_id,
            model_name=model_name,
        )

    @staticmethod
    async def list_usage_logs(
        db: AsyncSession,
        *,
        params: ListParams,
        user_id: int | None = None,
        api_key_id: int | None = None,
        model_name: str | None = None,
        effective_model: str | None = None,
        request_id: str | None = None,
    ) -> PaginatedResult[ApiCallLog]:
        return await UsageStatRepository(db).list_usage_logs(
            params=params,
            user_id=user_id,
            api_key_id=api_key_id,
            model_name=model_name,
            effective_model=effective_model,
            request_id=request_id,
        )

    @staticmethod
    async def get_usage_analytics(
        db: AsyncSession,
        *,
        user_id: int,
        range_name: UsageAnalyticsRange,
    ) -> UsageAnalyticsData:
        start, end, granularity = UsageStatService._build_usage_analytics_window(range_name, now())
        logs = await UsageStatRepository(db).list_analytics_logs(user_id=user_id, start=start, end=end)

        total_requests = len(logs)
        success_requests = sum(1 for log in logs if log.status == ApiCallLog.STATUS_SUCCESS)
        total_cost = sum(int(log.cost) for log in logs)

        per_model: dict[str, dict[str, int]] = defaultdict(
            lambda: {"request_count": 0, "total_cost": 0}
        )
        per_bucket: dict[datetime, dict[str, int]] = {
            bucket_start: {} for bucket_start in UsageStatService._iter_bucket_starts(start, end, granularity)
        }

        for log in logs:
            effective_model = UsageStatService._resolve_effective_model(log)
            bucket_start = UsageStatService._get_bucket_start(log.created_at, granularity)

            per_model[effective_model]["request_count"] += 1
            per_model[effective_model]["total_cost"] += int(log.cost)
            bucket_costs = per_bucket.setdefault(bucket_start, {})
            bucket_costs[effective_model] = bucket_costs.get(effective_model, 0) + int(log.cost)

        models = [
            UsageAnalyticsModel(
                effective_model=model_name,
                request_count=stats["request_count"],
                request_share=stats["request_count"] / total_requests if total_requests else 0,
                total_cost=stats["total_cost"],
            )
            for model_name, stats in sorted(
                per_model.items(),
                key=lambda item: (-item[1]["request_count"], -item[1]["total_cost"], item[0]),
            )
        ]

        buckets = [
            UsageAnalyticsBucket(
                bucket_start=bucket_start,
                label=UsageStatService._format_bucket_label(bucket_start, granularity),
                costs=[
                    UsageAnalyticsBucketCost(effective_model=model_name, total_cost=amount)
                    for model_name, amount in sorted(
                        per_bucket.get(bucket_start, {}).items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ],
            )
            for bucket_start in UsageStatService._iter_bucket_starts(start, end, granularity)
        ]

        return UsageAnalyticsData(
            range=range_name,
            granularity=granularity,
            start=start,
            end=end,
            currency="CNY",
            overview=UsageAnalyticsOverview(
                total_requests=total_requests,
                success_requests=success_requests,
                success_rate=success_requests / total_requests if total_requests else 0,
                total_cost=total_cost,
            ),
            models=models,
            buckets=buckets,
        )

    @staticmethod
    def _accumulate_bucket(bucket: dict[str, int], log: ApiCallLog) -> None:
        bucket["request_count"] += 1
        bucket["success_count"] += 1 if log.status == ApiCallLog.STATUS_SUCCESS else 0
        bucket["error_count"] += 1 if log.status == ApiCallLog.STATUS_ERROR else 0
        bucket["prompt_tokens"] += int(log.prompt_tokens)
        bucket["completion_tokens"] += int(log.completion_tokens)
        bucket["cached_tokens"] += int(log.cached_tokens)
        bucket["total_tokens"] += int(log.total_tokens)
        bucket["total_cost"] += int(log.cost)

    @staticmethod
    def _build_usage_analytics_window(
        range_name: UsageAnalyticsRange,
        reference_time: datetime,
    ) -> tuple[datetime, datetime, str]:
        bucket_count, granularity = _ANALYTICS_RANGES[range_name]
        if granularity == "hour":
            end = reference_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            start = end - timedelta(hours=bucket_count)
            return start, end, granularity

        end = reference_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        start = end - timedelta(days=bucket_count)
        return start, end, granularity

    @staticmethod
    def _iter_bucket_starts(start: datetime, end: datetime, granularity: str) -> list[datetime]:
        step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
        buckets: list[datetime] = []
        bucket_start = start
        while bucket_start < end:
            buckets.append(bucket_start)
            bucket_start += step
        return buckets

    @staticmethod
    def _get_bucket_start(value: datetime, granularity: str) -> datetime:
        if granularity == "hour":
            return value.replace(minute=0, second=0, microsecond=0)
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _format_bucket_label(value: datetime, granularity: str) -> str:
        return value.strftime("%H:%M" if granularity == "hour" else "%m-%d")

    @staticmethod
    def _resolve_effective_model(log: ApiCallLog) -> str:
        return log.selected_model or log.model_name
