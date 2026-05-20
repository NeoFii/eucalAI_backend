"""Admin dashboard endpoints — proxy elimination.

Ported from services/admin-service/src/controllers/dashboard.py.
All UserStatsGateway calls replaced with AdminDashboardService direct calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import BaseResponse
from app.common.utils.timezone import now
from app.core.db import get_db
from app.core.policies import require_active_admin
from app.model import AdminUser
from app.service.admin.dashboard_service import AdminDashboardService

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


class DashboardSummaryData(BaseModel):
    total_users: int = 0
    total_requests: int = 0
    total_revenue: int = 0
    total_provider_cost: int = 0
    new_users_today: int = 0
    requests_today: int = 0
    revenue_today: int = 0
    provider_cost_today: int = 0
    new_users_in_range: int = 0
    requests_in_range: int = 0
    revenue_in_range: int = 0
    provider_cost_in_range: int = 0


class DashboardSummaryResponse(BaseResponse):
    data: Optional[DashboardSummaryData] = None


class UserGrowthPoint(BaseModel):
    date: str
    count: int = 0


class UserGrowthResponse(BaseResponse):
    data: Optional[list[UserGrowthPoint]] = None


class UsageTrendsResponse(BaseResponse):
    data: Optional[dict] = None


class RpmTrendPointData(BaseModel):
    bucket_start: str
    request_count: int = 0
    rpm: float = 0.0


class RpmTrendData(BaseModel):
    bucket_seconds: int
    points: list[RpmTrendPointData] = []


class RpmTrendResponse(BaseResponse):
    data: Optional[RpmTrendData] = None


class TpmTrendPointData(BaseModel):
    bucket_start: str
    total_tokens: int = 0
    tpm: float = 0.0


class TpmTrendData(BaseModel):
    bucket_seconds: int
    points: list[TpmTrendPointData] = []


class TpmTrendResponse(BaseResponse):
    data: Optional[TpmTrendData] = None


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    raw = await AdminDashboardService.fetch_summary(db, start=start, end=end)
    return DashboardSummaryResponse(data=DashboardSummaryData(**raw))


@router.get("/user-growth", response_model=UserGrowthResponse)
async def get_user_growth(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserGrowthResponse:
    current = now()
    if end is None:
        end = current
    if start is None:
        start = end - timedelta(days=30)
    raw = await AdminDashboardService.fetch_user_growth(db, start=start, end=end)
    return UserGrowthResponse(data=[UserGrowthPoint(**item) for item in raw])


@router.get("/usage-trends", response_model=UsageTrendsResponse)
async def get_usage_trends(
    start: datetime | None = None,
    end: datetime | None = None,
    _admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UsageTrendsResponse:
    current = now()
    if end is None:
        end = current
    if start is None:
        start = end - timedelta(days=30)
    raw = await AdminDashboardService.fetch_usage_trends(db, start=start, end=end)
    return UsageTrendsResponse(data=raw)


@router.get("/rpm-trend", response_model=RpmTrendResponse)
async def get_rpm_trend(
    start: datetime,
    end: datetime,
    bucket_seconds: int = Query(60, ge=10, le=86400),
    _admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> RpmTrendResponse:
    raw = await AdminDashboardService.fetch_rpm_trend(
        db, start=start, end=end, bucket_seconds=bucket_seconds,
    )
    return RpmTrendResponse(data=RpmTrendData(**raw))


@router.get("/tpm-trend", response_model=TpmTrendResponse)
async def get_tpm_trend(
    start: datetime,
    end: datetime,
    bucket_seconds: int = Query(60, ge=10, le=86400),
    _admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> TpmTrendResponse:
    raw = await AdminDashboardService.fetch_tpm_trend(
        db, start=start, end=end, bucket_seconds=bucket_seconds,
    )
    return TpmTrendResponse(data=TpmTrendData(**raw))
