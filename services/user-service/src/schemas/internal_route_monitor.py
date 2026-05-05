"""Schemas for internal route-monitor endpoints (router/admin -> user-service)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class RouteRequestListItem(BaseModel):
    """Compact row for the route-monitor list view (no large preview field)."""

    id: int
    request_id: str
    user_id: int
    user_uid: str | None = None
    api_key_id: int | None = None
    model_name: str
    selected_model: str | None = None
    provider_slug: str | None = None
    upstream_model: str | None = None
    routing_tier: int | None = None
    score_source: str | None = None
    total_score_0_10: Decimal | None = None
    inference_error_code: str | None = None
    messages_count: int | None = None
    duration_ms: int | None = None
    upstream_latency_ms: int | None = None
    is_stream: bool
    status: int
    error_code: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: int = 0
    input_hash: str | None = None
    routing_detail: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouteRequestDetail(RouteRequestListItem):
    """Full detail view, including the (potentially large) request_preview blob."""

    request_preview: dict[str, Any] | None = None
    error_msg: str | None = None
    config_version: int | None = None
    config_source: str | None = None
    inference_config_version: int | None = None
    inference_config_source: str | None = None
    router_trace_id: str | None = None
    cached_tokens: int = 0
    provider_cost: int = 0
    cost_detail: dict[str, Any] | None = None
    ip: str | None = None
    updated_at: datetime | None = None


class RouteRequestListResponse(BaseModel):
    items: list[RouteRequestListItem]
    total: int
    page: int
    page_size: int


class RouteCompareItem(BaseModel):
    """One past request that shares the same input_hash as the focused request."""

    id: int
    request_id: str
    selected_model: str | None = None
    routing_tier: int | None = None
    total_score_0_10: Decimal | None = None
    score_source: str | None = None
    status: int
    duration_ms: int | None = None
    upstream_latency_ms: int | None = None
    cost: int = 0
    config_version: int | None = None
    inference_config_version: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouteCompareResponse(BaseModel):
    """Response for /compare/{request_id}.

    `target` is the focused row, `siblings` are other rows with the same
    input_hash (excluding the target). `siblings` is ordered most-recent first.
    """

    input_hash: str | None = None
    target: RouteCompareItem | None = None
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
    """A 1-wide histogram bucket on total_score_0_10. floor=0..9, label="0-1"."""

    floor: int
    count: int


class ProviderLatency(BaseModel):
    provider_slug: str
    count: int
    p50_ms: int | None = None
    p95_ms: int | None = None
    p99_ms: int | None = None


class RouteAggregateData(BaseModel):
    range_start: datetime
    range_end: datetime
    total: int
    success_total: int
    error_total: int
    by_tier: list[TierBucket]
    by_model: list[ModelBucket]
    by_score: list[ScoreBucket]
    by_provider_latency: list[ProviderLatency]
