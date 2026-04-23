"""User-facing billing schema split for user-service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field
from pydantic import Field

from user_service.schemas.common import DateTimeModel


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


class TopupOrderItem(DateTimeModel):
    id: int
    order_no: str
    amount: int
    status: int
    payment_channel: str
    payment_no: Optional[str] = None
    paid_at: Optional[datetime] = None
    remark: Optional[str] = None
    created_at: datetime
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


class ApiCallLogItem(DateTimeModel):
    id: int
    request_id: str
    api_key_id: Optional[int] = None
    model_name: str
    selected_model: Optional[str] = None
    provider_slug: Optional[str] = None
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

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ApiCallLogItem",
    "BalanceResponseData",
    "BalanceTransactionItem",
    "TopupOrderItem",
    "UsageStatItem",
    "VoucherRedeemRequest",
    "VoucherRedeemResponseData",
]
