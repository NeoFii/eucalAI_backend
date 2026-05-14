"""Schemas for internal call log endpoints."""

from decimal import Decimal

from pydantic import BaseModel, Field


class InternalCreateCallLogRequest(BaseModel):
    request_id: str = Field(max_length=64)
    user_id: int
    api_key_id: int | None = None
    model_name: str = Field(max_length=64)
    selected_model: str | None = Field(None, max_length=64)
    provider_slug: str | None = Field(None, max_length=32)
    upstream_model: str | None = Field(None, max_length=64)
    is_stream: bool = False
    ip: str | None = Field(None, max_length=45)
    config_version: int | None = None
    config_source: str | None = Field(None, max_length=32)
    inference_config_version: int | None = None
    inference_config_source: str | None = Field(None, max_length=32)
    routing_tier: int | None = None
    score_source: str | None = Field(None, max_length=32)
    router_trace_id: str | None = Field(None, max_length=64)
    inference_error_code: str | None = Field(None, max_length=32)
    input_hash: str | None = Field(None, max_length=32)
    status: int | None = None


class InternalUpdateCallLogRequest(BaseModel):
    status: int | None = None
    selected_model: str | None = Field(None, max_length=64)
    provider_slug: str | None = Field(None, max_length=32)
    upstream_model: str | None = Field(None, max_length=64)
    config_version: int | None = None
    config_source: str | None = Field(None, max_length=32)
    inference_config_version: int | None = None
    inference_config_source: str | None = Field(None, max_length=32)
    routing_tier: int | None = None
    score_source: str | None = Field(None, max_length=32)
    total_score_0_10: Decimal | float | None = None
    router_trace_id: str | None = Field(None, max_length=64)
    inference_error_code: str | None = Field(None, max_length=32)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    upstream_latency_ms: int | None = None
    messages_count: int | None = None
    error_code: str | None = Field(None, max_length=32)
    error_msg: str | None = Field(None, max_length=1024)
    cost: int | None = None
    provider_cost: int | None = None
    cost_detail: dict | None = None
    routing_detail: dict | None = None
    request_preview: dict | None = None
    input_hash: str | None = Field(None, max_length=32)


class InternalBatchCallLogRequest(BaseModel):
    entries: list[dict] = Field(max_length=500)
