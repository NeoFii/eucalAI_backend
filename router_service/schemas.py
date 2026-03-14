"""Router service schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from common.utils.timezone import format_iso


class DateTimeModel(BaseModel):
    """Base model with datetime ISO serialization."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class RouterBaseResponse(BaseModel):
    """Common response wrapper."""

    code: int = Field(default=200)
    message: str = Field(default="success")


class OpenAIModelCard(BaseModel):
    """OpenAI-compatible model card."""

    id: str
    object: str = "model"
    owned_by: str = "eucal-router"


class OpenAIModelListResponse(BaseModel):
    """OpenAI-compatible model list."""

    object: str = "list"
    data: list[OpenAIModelCard]


class RouterChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False


class RouterCompletionRequest(BaseModel):
    """OpenAI-compatible completion request."""

    model_config = ConfigDict(extra="allow")

    model: str
    prompt: str | list[str]
    stream: bool = False
    suffix: Optional[str] = None


class UsageEventItem(DateTimeModel):
    """Usage event response item."""

    id: int
    request_id: str
    router_api_key_id: Optional[int] = None
    provider_slug: Optional[str] = None
    requested_model: str
    resolved_model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_input: float
    cost_output: float
    cost_total: float
    currency: str
    status_code: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime


class UsageEventsResponseData(BaseModel):
    """Usage event list payload."""

    items: list[UsageEventItem]
    total: int


class UsageEventsResponse(RouterBaseResponse):
    """Usage event list response."""

    data: UsageEventsResponseData


class UsageSummaryData(BaseModel):
    """Aggregated usage summary."""

    total_requests: int
    success_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost: float
    currency: str


class UsageSummaryResponse(RouterBaseResponse):
    """Usage summary response."""

    data: UsageSummaryData


class BillingLedgerItem(DateTimeModel):
    """Ledger row response item."""

    id: int
    usage_event_id: Optional[int] = None
    router_api_key_id: Optional[int] = None
    direction: str
    amount: float
    currency: str
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    description: Optional[str] = None
    created_at: datetime


class BillingLedgerResponseData(BaseModel):
    """Billing ledger payload."""

    items: list[BillingLedgerItem]
    total: int


class BillingLedgerResponse(RouterBaseResponse):
    """Billing ledger response."""

    data: BillingLedgerResponseData


class RouterApiKeyItem(DateTimeModel):
    """Router API key item."""

    id: int
    name: str
    token_preview: str
    is_active: bool
    is_deleted: bool = False
    billing_mode: str
    balance: Optional[float] = None
    daily_quota_tokens: Optional[int] = None
    monthly_quota_tokens: Optional[int] = None
    daily_quota_cost: Optional[float] = None
    monthly_quota_cost: Optional[float] = None
    rate_limit_rpm: Optional[int] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RouterApiKeyCreateRequest(BaseModel):
    """Create router API key request."""

    name: str = Field(..., min_length=1, max_length=100)


class RouterApiKeyUpdateRequest(BaseModel):
    """Update router API key request."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class RouterApiKeyListResponseData(BaseModel):
    """Router API key list payload."""

    items: list[RouterApiKeyItem]


class RouterApiKeyListResponse(RouterBaseResponse):
    """Router API key list response."""

    data: RouterApiKeyListResponseData


class RouterApiKeyCreateResponseData(BaseModel):
    """Router API key create payload."""

    item: RouterApiKeyItem
    api_key: str


class RouterApiKeyCreateResponse(RouterBaseResponse):
    """Router API key create response."""

    data: RouterApiKeyCreateResponseData


class RouterApiKeyUpdateResponse(RouterBaseResponse):
    """Router API key update response."""

    data: RouterApiKeyItem


class RouterApiKeyRevealResponseData(BaseModel):
    """Router API key reveal payload."""

    item: RouterApiKeyItem
    api_key: str


class RouterApiKeyRevealResponse(RouterBaseResponse):
    """Router API key reveal response."""

    data: RouterApiKeyRevealResponseData


class RouterApiKeyDeleteResponseData(BaseModel):
    """Router API key delete payload."""

    deleted: bool


class RouterApiKeyDeleteResponse(RouterBaseResponse):
    """Router API key delete response."""

    data: RouterApiKeyDeleteResponseData
