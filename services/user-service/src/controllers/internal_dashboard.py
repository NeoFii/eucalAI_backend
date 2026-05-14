"""Internal dashboard analytics endpoints."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from controllers.internal import verify_internal_secret
from core.dependencies import get_db_session
from repositories.usage_stat_repository import UsageStatRepository
from repositories.user_repository import UserRepository
from schemas.internal_dashboard import (
    DailyUsageTrendItem,
    DashboardSummaryResponse,
    ModelCallStatItem,
    RpmTrendPoint,
    RpmTrendResponse,
    TpmTrendPoint,
    TpmTrendResponse,
    UsageTrendsResponse,
    UserGrowthPointResponse,
)

logger = logging.getLogger("user_service.internal.dashboard")

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    summary="Platform dashboard summary",
)
async def get_dashboard_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardSummaryResponse:
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    user_repo = UserRepository(db)
    stat_repo = UsageStatRepository(db)

    total_users = await user_repo.count_all()
    new_users_today = await user_repo.count_since(today_start)

    if start is not None or end is not None:
        new_users_in_range = await user_repo.count_in_range(start=start, end=end)
    else:
        new_users_in_range = new_users_today

    call_stats = await stat_repo.get_platform_summary(
        today_start=today_start,
        range_start=start,
        range_end=end,
    )

    return DashboardSummaryResponse(
        total_users=total_users,
        new_users_today=new_users_today,
        new_users_in_range=new_users_in_range,
        **call_stats,
    )


@router.get(
    "/dashboard/user-growth",
    response_model=list[UserGrowthPointResponse],
    summary="Daily user registration growth",
)
async def get_user_growth(
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[UserGrowthPointResponse]:
    if end is None:
        end = now()
    if start is None:
        start = end - timedelta(days=30)

    user_repo = UserRepository(db)
    daily = await user_repo.get_daily_registrations(start=start, end=end)
    users_before = await user_repo.count_all() - sum(d["count"] for d in daily)

    cumulative = max(users_before, 0)
    result = []
    for d in daily:
        cumulative += d["count"]
        result.append(UserGrowthPointResponse(
            date=d["date"],
            new_users=d["count"],
            cumulative=cumulative,
        ))
    return result


@router.get(
    "/dashboard/usage-trends",
    response_model=UsageTrendsResponse,
    summary="Platform usage trends",
)
async def get_usage_trends(
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> UsageTrendsResponse:
    if end is None:
        end = now()
    if start is None:
        start = end - timedelta(days=30)

    range_seconds = int((end - start).total_seconds())
    if range_seconds <= 86400:
        bucket_seconds = 3600
    elif range_seconds <= 259200:
        bucket_seconds = 7200
    else:
        bucket_seconds = 86400

    stat_repo = UsageStatRepository(db)
    daily = await stat_repo.get_bucketed_platform_stats(
        start=start, end=end, bucket_seconds=bucket_seconds,
    )
    by_model = await stat_repo.get_model_call_stats(start=start, end=end)

    return UsageTrendsResponse(
        bucket_seconds=bucket_seconds,
        daily=[DailyUsageTrendItem(**d) for d in daily],
        by_model=[ModelCallStatItem(**m) for m in by_model],
    )


@router.get(
    "/dashboard/rpm-trend",
    response_model=RpmTrendResponse,
    summary="Platform RPM time-bucketed trend",
)
async def get_rpm_trend(
    start: datetime,
    end: datetime,
    bucket_seconds: int = Query(60, ge=10, le=86400),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> RpmTrendResponse:
    """Return per-bucket request counts and RPM over [start, end).

    Bucket width is fixed at ``bucket_seconds``. Empty buckets (no requests)
    are not returned by the SQL aggregation; the admin frontend fills the
    time axis from start..end on the client side so the chart x-axis stays
    continuous regardless of activity.
    """
    if end <= start:
        return RpmTrendResponse(bucket_seconds=bucket_seconds, points=[])
    points = await UsageStatRepository(db).get_rpm_trend(
        start=start, end=end, bucket_seconds=bucket_seconds,
    )
    return RpmTrendResponse(
        bucket_seconds=bucket_seconds,
        points=[RpmTrendPoint(**p) for p in points],
    )


@router.get(
    "/dashboard/tpm-trend",
    response_model=TpmTrendResponse,
    summary="Platform TPM time-bucketed trend",
)
async def get_tpm_trend(
    start: datetime,
    end: datetime,
    bucket_seconds: int = Query(60, ge=10, le=86400),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> TpmTrendResponse:
    """Return per-bucket token counts and TPM over [start, end)."""
    if end <= start:
        return TpmTrendResponse(bucket_seconds=bucket_seconds, points=[])
    points = await UsageStatRepository(db).get_tpm_trend(
        start=start, end=end, bucket_seconds=bucket_seconds,
    )
    return TpmTrendResponse(
        bucket_seconds=bucket_seconds,
        points=[TpmTrendPoint(**p) for p in points],
    )
