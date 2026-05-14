"""Schemas for internal dashboard endpoints."""

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    # 历史累计（不受 start/end 影响）
    total_users: int
    total_requests: int
    total_revenue: int
    total_provider_cost: int

    # 今日数值（保留兼容旧调用方）
    new_users_today: int
    requests_today: int
    revenue_today: int
    provider_cost_today: int

    # 选定区间内数值
    new_users_in_range: int = 0
    requests_in_range: int = 0
    revenue_in_range: int = 0
    provider_cost_in_range: int = 0


class UserGrowthPointResponse(BaseModel):
    date: str
    new_users: int
    cumulative: int


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


class UsageTrendsResponse(BaseModel):
    daily: list[DailyUsageTrendItem]
    by_model: list[ModelCallStatItem]


class RpmTrendPoint(BaseModel):
    bucket_start: str  # ISO 8601, naive (DB-local) timestamp aligned to the bucket grid
    request_count: int
    rpm: float


class RpmTrendResponse(BaseModel):
    bucket_seconds: int
    points: list[RpmTrendPoint]


class TpmTrendPoint(BaseModel):
    bucket_start: str
    total_tokens: int
    tpm: float


class TpmTrendResponse(BaseModel):
    bucket_seconds: int
    points: list[TpmTrendPoint]
