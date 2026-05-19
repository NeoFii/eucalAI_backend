"""Admin dashboard service — proxy elimination layer.

Replaces UserStatsGateway HTTP calls with direct Phase 3 repository calls.
Each method composes repository aggregate calls (no HTTP, no N+1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.utils.timezone import now
from api_service.repositories.billing_repository import BillingRepository
from api_service.repositories.user_repository import UserRepository


class AdminDashboardService:
    """5 staticmethods replacing UserStatsGateway HTTP calls."""

    @staticmethod
    async def fetch_summary(
        db: AsyncSession,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        current = now()
        if end is None:
            end = current
        if start is None:
            start = end - timedelta(days=30)

        today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)

        user_repo = UserRepository(db)
        billing_repo = BillingRepository(db)

        total_users = await user_repo.count_all()
        new_users_today = await user_repo.count_since(today_start)
        new_users_in_range = await user_repo.count_in_range(start=start, end=end)

        # Single-query aggregate for platform stats
        platform = await billing_repo.stat_get_platform_summary(
            today_start=today_start,
            range_start=start,
            range_end=end,
        )

        return {
            "total_users": total_users,
            "total_requests": platform["total_requests"],
            "total_revenue": platform["total_revenue"],
            "total_provider_cost": platform["total_provider_cost"],
            "new_users_today": new_users_today,
            "requests_today": platform["requests_today"],
            "revenue_today": platform["revenue_today"],
            "provider_cost_today": platform["provider_cost_today"],
            "new_users_in_range": new_users_in_range,
            "requests_in_range": platform["requests_in_range"],
            "revenue_in_range": platform["revenue_in_range"],
            "provider_cost_in_range": platform["provider_cost_in_range"],
        }

    @staticmethod
    async def fetch_user_growth(
        db: AsyncSession, *, start: datetime, end: datetime,
    ) -> list[dict]:
        return await UserRepository(db).get_daily_registrations(start=start, end=end)

    @staticmethod
    async def fetch_usage_trends(
        db: AsyncSession, *, start: datetime, end: datetime, bucket_seconds: int = 86400,
    ) -> dict:
        billing_repo = BillingRepository(db)
        daily = await billing_repo.stat_get_bucketed_platform_stats(
            start=start, end=end, bucket_seconds=bucket_seconds,
        )
        by_model = await billing_repo.stat_get_model_call_stats(start=start, end=end)
        return {
            "bucket_seconds": bucket_seconds,
            "daily": daily,
            "by_model": by_model,
        }

    @staticmethod
    async def fetch_rpm_trend(
        db: AsyncSession, *, start: datetime, end: datetime, bucket_seconds: int = 60,
    ) -> dict:
        points = await BillingRepository(db).stat_get_rpm_trend(
            start=start, end=end, bucket_seconds=bucket_seconds,
        )
        return {"bucket_seconds": bucket_seconds, "points": points}

    @staticmethod
    async def fetch_tpm_trend(
        db: AsyncSession, *, start: datetime, end: datetime, bucket_seconds: int = 60,
    ) -> dict:
        points = await BillingRepository(db).stat_get_tpm_trend(
            start=start, end=end, bucket_seconds=bucket_seconds,
        )
        return {"bucket_seconds": bucket_seconds, "points": points}


__all__ = ["AdminDashboardService"]
