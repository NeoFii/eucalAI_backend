"""User-facing billing schema split for user-service."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, computed_field
from pydantic import Field

from schemas.common import DateTimeModel


class BalanceResponseData(BaseModel):
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int

    @computed_field
    @property
    def available_balance(self) -> int:
        return self.balance - self.frozen_amount


class BalanceTransactionItem(DateTimeModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoucherRedeemRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=64)


class VoucherRedeemResponseData(DateTimeModel):
    id: int
    amount: int
    status: int
    redeemed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class VoucherRedemptionItem(DateTimeModel):
    id: int
    code_prefix: str
    code_suffix: str
    amount: int
    status: int
    redeemed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TopupOrderItem(DateTimeModel):
    id: int
    order_no: str
    amount: int
    status: int
    payment_channel: str
    payment_no: Optional[str] = None
    paid_at: Optional[datetime] = None
    remark: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UsageStatItem(DateTimeModel):
    id: int
    api_key_id: Optional[int] = None
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


UsageAnalyticsRange = Literal["8h", "24h", "7d", "30d"]


class UsageAnalyticsOverview(BaseModel):
    total_requests: int
    success_requests: int
    success_rate: float
    total_cost: int


class UsageAnalyticsModel(BaseModel):
    effective_model: str
    request_count: int
    request_share: float
    total_cost: int


class UsageAnalyticsBucketCost(BaseModel):
    effective_model: str
    total_cost: int


class UsageAnalyticsBucket(DateTimeModel):
    bucket_start: datetime
    label: str
    costs: list[UsageAnalyticsBucketCost]


class UsageAnalyticsData(DateTimeModel):
    range: Optional[str] = None
    granularity: str
    start: datetime
    end: datetime
    currency: str
    overview: UsageAnalyticsOverview
    models: list[UsageAnalyticsModel]
    buckets: list[UsageAnalyticsBucket]


class ApiCallLogItem(DateTimeModel):
    id: int
    request_id: str
    api_key_id: Optional[int] = None
    api_key_name: Optional[str] = None
    model_name: str = Field(exclude=True)
    selected_model: Optional[str] = Field(default=None, exclude=True)
    provider_slug: Optional[str] = Field(default=None, exclude=True)
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost: int
    status: int
    duration_ms: Optional[int] = None
    is_stream: bool
    routing_tier: Optional[int] = None
    config_version: Optional[int] = None
    config_source: Optional[str] = None
    router_trace_id: Optional[str] = None
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def effective_model(self) -> str:
        return self.selected_model or self.model_name

    @classmethod
    def from_orm_instance(cls, obj: object) -> "ApiCallLogItem":
        data = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
        key_rel = getattr(obj, "api_key", None)
        data["api_key_name"] = key_rel.name if key_rel else None
        return cls.model_validate(data)

    model_config = ConfigDict(from_attributes=True)


class AlipayCreateOrderRequest(BaseModel):
    amount: int = Field(..., ge=1_000_000, le=10_000_000_000, description="Amount in micro-yuan")
    device: Literal["pc", "mobile"] = Field(default="pc", description="Device type")


class AlipayCreateOrderResponse(BaseModel):
    order_no: str
    form_html: str


class AlipayOrderStatusResponse(DateTimeModel):
    order_no: str
    status: int
    amount: int
    paid_at: Optional[datetime] = None


__all__ = [
    "AlipayCreateOrderRequest",
    "AlipayCreateOrderResponse",
    "AlipayOrderStatusResponse",
    "ApiCallLogItem",
    "BalanceResponseData",
    "BalanceTransactionItem",
    "TopupOrderItem",
    "UsageAnalyticsBucket",
    "UsageAnalyticsBucketCost",
    "UsageAnalyticsData",
    "UsageAnalyticsModel",
    "UsageAnalyticsOverview",
    "UsageAnalyticsRange",
    "UsageStatItem",
    "VoucherRedeemRequest",
    "VoucherRedeemResponseData",
    "VoucherRedemptionItem",
]
