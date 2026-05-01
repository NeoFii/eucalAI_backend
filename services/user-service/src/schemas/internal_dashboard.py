"""Schemas for internal dashboard endpoints."""

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    total_users: int
    new_users_today: int
    total_requests: int
    requests_today: int
    total_revenue: int
    revenue_today: int
    total_provider_cost: int
    provider_cost_today: int


class UserGrowthPointResponse(BaseModel):
    date: str
    new_users: int
    cumulative: int


class DailyUsageTrendItem(BaseModel):
    date: str
    request_count: int
    success_count: int
    error_count: int
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
