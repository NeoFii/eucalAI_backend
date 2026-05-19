"""Admin-facing schemas for the route-monitor panel.

Ported from services/admin-service/src/schemas/route_monitor.py.
Rewrites: AdminBaseResponse -> BaseResponse; import paths -> api_service.*
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from api_service.common.schemas import BaseResponse, DateTimeModel


class RouteRequestListItem(DateTimeModel):
    """Compact row for the list view."""

    id: int
    request_id: str
    user_uid: Optional[str] = None
    api_key_id: Optional[int] = None
    model_name: str = ""
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
    is_stream: bool = False
    status: Optional[int] = None
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cost: int = 0
    input_hash: Optional[str] = None
    routing_detail: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None


class RouteRequestDetail(RouteRequestListItem):
    """Full detail view."""

    request_preview: Optional[dict[str, Any]] = None
    config_version: Optional[int] = None
    config_source: Optional[str] = None
    inference_config_version: Optional[int] = None
    inference_config_source: Optional[str] = None
    router_trace_id: Optional[str] = None
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
    status: Optional[int] = None
    duration_ms: Optional[int] = None
    upstream_latency_ms: Optional[int] = None
    cost: int = 0
    config_version: Optional[int] = None
    inference_config_version: Optional[int] = None
    created_at: Optional[datetime] = None


class RouteCompareData(BaseModel):
    input_hash: Optional[str] = None
    target: Optional[RouteCompareItem] = None
    siblings: list[RouteCompareItem] = []


class RouteAggregateData(DateTimeModel):
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None
    total: int = 0
    success_total: int = 0
    error_total: int = 0
    by_time: list[dict] = []
    by_model: list[dict] = []
    by_score: list[dict] = []
    by_provider_latency: list[dict] = []


# --- Response wrappers ---


class RouteRequestListResponse(BaseResponse):
    data: Optional[dict] = None


class RouteRequestDetailResponse(BaseResponse):
    data: Optional[RouteRequestDetail] = None


class RouteAggregateResponse(BaseResponse):
    data: Optional[RouteAggregateData] = None


class RouteCompareResponse(BaseResponse):
    data: Optional[RouteCompareData] = None
