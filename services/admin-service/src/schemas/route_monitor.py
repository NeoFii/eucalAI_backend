"""Admin-facing schemas for the route-monitor panel."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from common.api import PaginatedResponse
from schemas.common import AdminBaseResponse, DateTimeModel


class RouteRequestListItem(DateTimeModel):
    """Compact row for the list view (no large preview field)."""

    id: int
    request_id: str
    user_uid: Optional[str] = None
    api_key_id: Optional[int] = None
    model_name: str
    selected_model: Optional[str] = None
    provider_slug: Optional[str] = None
    upstream_model: Optional[str] = None
    routing_tier: Optional[int] = None
    score_source: Optional[str] = None
    total_score_0_10: Optional[Decimal] = None
    inference_error_code: Optional[str] = None
    messages_count: Optional[int] = None
    duration_ms: Optional[int] = None
    upstream_latency_ms: Optional[int] = None
    is_stream: bool
    status: int
    error_code: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: int = 0
    input_hash: Optional[str] = None
    routing_detail: Optional[dict[str, Any]] = None
    created_at: datetime


class RouteRequestDetail(RouteRequestListItem):
    """Full detail view including the (potentially large) request_preview blob."""

    request_preview: Optional[dict[str, Any]] = None
    error_msg: Optional[str] = None
    config_version: Optional[int] = None
    config_source: Optional[str] = None
    inference_config_version: Optional[int] = None
    inference_config_source: Optional[str] = None
    router_trace_id: Optional[str] = None
    cached_tokens: int = 0
    provider_cost: int = 0
    cost_detail: Optional[dict[str, Any]] = None
    ip: Optional[str] = None
    updated_at: Optional[datetime] = None


class RouteCompareItem(DateTimeModel):
    id: int
    request_id: str
    selected_model: Optional[str] = None
    routing_tier: Optional[int] = None
    total_score_0_10: Optional[Decimal] = None
    score_source: Optional[str] = None
    status: int
    duration_ms: Optional[int] = None
    upstream_latency_ms: Optional[int] = None
    cost: int = 0
    config_version: Optional[int] = None
    inference_config_version: Optional[int] = None
    created_at: datetime


class RouteCompareData(BaseModel):
    input_hash: Optional[str] = None
    target: Optional[RouteCompareItem] = None
    siblings: list[RouteCompareItem]


class TierBucket(BaseModel):
    routing_tier: int
    count: int
    success_count: int
    error_count: int


class ModelBucket(BaseModel):
    selected_model: str
    count: int


class ScoreBucket(BaseModel):
    floor: int
    count: int


class ProviderLatency(BaseModel):
    provider_slug: str
    count: int
    p50_ms: Optional[int] = None
    p95_ms: Optional[int] = None
    p99_ms: Optional[int] = None


class RouteAggregateData(DateTimeModel):
    range_start: datetime
    range_end: datetime
    total: int
    success_total: int
    error_total: int
    by_tier: list[TierBucket]
    by_model: list[ModelBucket]
    by_score: list[ScoreBucket]
    by_provider_latency: list[ProviderLatency]


# --- Response wrappers ---


class RouteRequestListResponse(AdminBaseResponse):
    data: Optional[PaginatedResponse[RouteRequestListItem]] = None


class RouteRequestDetailResponse(AdminBaseResponse):
    data: Optional[RouteRequestDetail] = None


class RouteAggregateResponse(AdminBaseResponse):
    data: Optional[RouteAggregateData] = None


class RouteCompareResponse(AdminBaseResponse):
    data: Optional[RouteCompareData] = None
