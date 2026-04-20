"""Admin billing schema split for user-service."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from user_service.schemas.billing import ApiCallLogItem, BalanceTransactionItem, TopupOrderItem, UsageStatItem


class AdminBalanceTransactionItem(BalanceTransactionItem):
    operator_id: Optional[int] = None


class AdminTopupOrderItem(TopupOrderItem):
    user_id: int
    operator_id: Optional[int] = None


class AdminUsageStatItem(UsageStatItem):
    user_id: int


class AdminApiCallLogItem(ApiCallLogItem):
    user_id: int
    ip: Optional[str] = None
    cost_detail: Optional[dict[str, Any]] = None


class AdminTopupRequest(BaseModel):
    amount: int = Field(..., gt=0)
    remark: str = Field(default="")


class AdminAdjustBalanceRequest(BaseModel):
    amount: int = Field(..., description="正数增加余额，负数扣减余额")
    remark: str = Field(..., min_length=1, max_length=255)


__all__ = [
    "AdminAdjustBalanceRequest",
    "AdminApiCallLogItem",
    "AdminBalanceTransactionItem",
    "AdminTopupOrderItem",
    "AdminTopupRequest",
    "AdminUsageStatItem",
]
