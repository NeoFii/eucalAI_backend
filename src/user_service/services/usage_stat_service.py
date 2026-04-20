"""Usage-stat aggregation and query helpers for user-service."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.models import ApiCallLog, UsageStat
from user_service.repositories import UsageStatRepository


class UsageStatService:
    """Aggregate api_call_logs into hourly usage buckets."""

    @staticmethod
    async def aggregate_hour(db: AsyncSession, stat_hour: datetime) -> None:
        next_hour = stat_hour + timedelta(hours=1)
        logs = list(
            (
                await db.execute(
                    select(ApiCallLog).where(
                        ApiCallLog.created_at >= stat_hour,
                        ApiCallLog.created_at < next_hour,
                    )
                )
            )
            .scalars()
            .all()
        )

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
            existing = (
                await db.execute(
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
            if existing is None:
                existing = UsageStat(
                    user_id=user_id,
                    api_key_id=api_key_id,
                    account_api_key_id=api_key_id or 0,
                    model_name=model_name,
                    stat_hour=stat_hour,
                )
                db.add(existing)
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
        user_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        api_key_id: int | None = None,
        model_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ApiCallLog], int]:
        return await UsageStatRepository(db).list_usage_logs(
            user_id=user_id,
            start=start,
            end=end,
            api_key_id=api_key_id,
            model_name=model_name,
            page=page,
            page_size=page_size,
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
