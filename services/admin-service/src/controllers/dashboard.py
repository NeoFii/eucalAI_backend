"""Admin dashboard endpoints (facade over user-service)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from gateways.user_management import UserStatsGateway
from models import AdminUser
from core.policies import require_active_admin
from schemas.common import AdminBaseResponse
from common.utils.timezone import format_iso, now

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_stats_gateway = UserStatsGateway()


class DashboardSummaryData(BaseModel):
    total_users: int
    total_requests: int
    total_revenue: int
    total_provider_cost: int

    new_users_today: int
    requests_today: int
    revenue_today: int
    provider_cost_today: int

    new_users_in_range: int = 0
    requests_in_range: int = 0
    revenue_in_range: int = 0
    provider_cost_in_range: int = 0


class DashboardSummaryResponse(AdminBaseResponse):
    data: Optional[DashboardSummaryData] = None


class UserGrowthPoint(BaseModel):
    date: str
    new_users: int
    cumulative: int


class UserGrowthResponse(AdminBaseResponse):
    data: Optional[list[UserGrowthPoint]] = None


class DailyUsageTrendItem(BaseModel):
    date: str
    request_count: int
    pending_count: int = 0
    success_count: int
    error_count: int
    refunded_count: int = 0
    aborted_count: int = 0
    prompt_tokens: int
    completion_tokens: int
    total_revenue: int
    total_provider_cost: int


class ModelCallStatItem(BaseModel):
    model: str
    request_count: int
    total_revenue: int
    total_provider_cost: int
    prompt_tokens: int
    completion_tokens: int


class UsageTrendsData(BaseModel):
    daily: list[DailyUsageTrendItem]
    by_model: list[ModelCallStatItem]


class UsageTrendsResponse(AdminBaseResponse):
    data: Optional[UsageTrendsData] = None


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
) -> DashboardSummaryResponse:
    current = now()
    if end is None:
        end = current
    if start is None:
        start = end - timedelta(days=30)

    gw = _stats_gateway
    raw = await gw.fetch_dashboard_summary(format_iso(start), format_iso(end))
    return DashboardSummaryResponse(code=200, message="success", data=DashboardSummaryData(**raw))


@router.get("/user-growth", response_model=UserGrowthResponse)
async def get_user_growth(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
) -> UserGrowthResponse:
    current = now()
    if end is None:
        end = current
    if start is None:
        start = end - timedelta(days=30)

    gw = _stats_gateway
    raw = await gw.fetch_user_growth(format_iso(start), format_iso(end))
    return UserGrowthResponse(
        code=200,
        message="success",
        data=[UserGrowthPoint(**item) for item in raw],
    )


@router.get("/usage-trends", response_model=UsageTrendsResponse)
async def get_usage_trends(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
) -> UsageTrendsResponse:
    current = now()
    if end is None:
        end = current
    if start is None:
        start = end - timedelta(days=30)

    gw = _stats_gateway
    raw = await gw.fetch_usage_trends(format_iso(start), format_iso(end))
    return UsageTrendsResponse(code=200, message="success", data=UsageTrendsData(**raw))


class RpmTrendPointData(BaseModel):
    bucket_start: str
    request_count: int
    rpm: float


class RpmTrendData(BaseModel):
    bucket_seconds: int
    points: list[RpmTrendPointData]


class RpmTrendResponse(AdminBaseResponse):
    data: Optional[RpmTrendData] = None


@router.get("/rpm-trend", response_model=RpmTrendResponse)
async def get_rpm_trend(
    start: datetime,
    end: datetime,
    bucket_seconds: int = Query(60, ge=10, le=86400),
    _admin: AdminUser = Depends(require_active_admin),
) -> RpmTrendResponse:
    """Return per-bucket RPM samples over [start, end)."""
    gw = _stats_gateway
    raw = await gw.fetch_rpm_trend(
        format_iso(start), format_iso(end), bucket_seconds,
    )
    return RpmTrendResponse(code=200, message="success", data=RpmTrendData(**raw))
