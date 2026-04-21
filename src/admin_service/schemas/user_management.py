"""User management schemas for admin-service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from admin_service.schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse


# --- Request schemas ---


class UpdateUserStatusRequest(BaseModel):
    status: int = Field(..., description="0=禁用 1=启用")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("status must be 0 or 1")
        return v


class ResetUserPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")


class TopupUserRequest(BaseModel):
    amount: int = Field(..., gt=0, description="充值金额（分）")
    remark: str = Field(default="", description="备注")


class AdjustUserBalanceRequest(BaseModel):
    amount: int = Field(..., description="正数增加余额，负数扣减余额")
    remark: str = Field(..., min_length=1, max_length=255, description="备注")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount must not be 0")
        return v


# --- Response schemas ---


class UserListItem(DateTimeModel):
    uid: int
    email: str
    status: int
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    balance: int
    created_at: datetime


class UserListResponse(AdminBaseResponse):
    data: Optional[PaginatedResponse[UserListItem]] = None


class UserDetailData(DateTimeModel):
    uid: int
    email: str
    status: int
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime


class UserDetailResponse(AdminBaseResponse):
    data: Optional[UserDetailData] = None


class UserApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime


class UserApiKeyListResponse(AdminBaseResponse):
    data: Optional[list[UserApiKeyItem]] = None


class UserTransactionItem(DateTimeModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    created_at: datetime


class UserTransactionListResponse(AdminBaseResponse):
    data: Optional[PaginatedResponse[UserTransactionItem]] = None


class UserUsageLogItem(DateTimeModel):
    id: int
    user_id: int
    request_id: str
    api_key_id: Optional[int] = None
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost: int
    status: int
    duration_ms: Optional[int] = None
    is_stream: bool
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    ip: Optional[str] = None
    cost_detail: Optional[dict[str, Any]] = None
    created_at: datetime


class UserUsageLogListResponse(AdminBaseResponse):
    data: Optional[PaginatedResponse[UserUsageLogItem]] = None


class UserUsageStatItem(DateTimeModel):
    id: int
    user_id: int
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


class UserUsageStatListResponse(AdminBaseResponse):
    data: Optional[list[UserUsageStatItem]] = None


class UserOperationResponse(AdminBaseResponse):
    pass
