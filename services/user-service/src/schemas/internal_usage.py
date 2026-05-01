"""Schemas for internal usage endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InternalUsageLogItem(BaseModel):
    id: int
    user_id: int
    request_id: str
    api_key_id: int | None = None
    model_name: str
    selected_model: str | None = None
    provider_slug: str | None = None
    upstream_model: str | None = None
    config_version: int | None = None
    config_source: str | None = None
    inference_config_version: int | None = None
    inference_config_source: str | None = None
    routing_tier: int | None = None
    score_source: str | None = None
    router_trace_id: str | None = None
    inference_error_code: str | None = None
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost: int
    status: int
    duration_ms: int | None = None
    is_stream: bool
    error_code: str | None = None
    error_msg: str | None = None
    ip: str | None = None
    cost_detail: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InternalUsageLogListResponse(BaseModel):
    items: list[InternalUsageLogItem]
    total: int
    page: int
    page_size: int


class InternalUsageStatItem(BaseModel):
    id: int
    user_id: int
    api_key_id: int | None = None
    model_name: str
    stat_hour: datetime
    request_count: int
    success_count: int
    error_count: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    total_cost: int

    model_config = ConfigDict(from_attributes=True)
