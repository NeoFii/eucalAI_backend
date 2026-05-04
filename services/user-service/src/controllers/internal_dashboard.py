"""Internal dashboard analytics endpoints."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
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

    stat_repo = UsageStatRepository(db)
    daily = await stat_repo.get_daily_platform_stats(start=start, end=end)
    by_model = await stat_repo.get_model_call_stats(start=start, end=end)

    return UsageTrendsResponse(
        daily=[DailyUsageTrendItem(**d) for d in daily],
        by_model=[ModelCallStatItem(**m) for m in by_model],
    )
