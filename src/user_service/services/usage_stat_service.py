"""Usage-stat aggregation and query helpers for user-service."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.models import ApiCallLog, UsageStat


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
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_all_stats(
        db: AsyncSession,
        start: datetime,
        end: datetime,
        user_id: int | None = None,
        model_name: str | None = None,
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
        return list((await db.execute(query)).scalars().all())

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
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

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
