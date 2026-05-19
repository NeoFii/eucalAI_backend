"""User management schemas for admin-service (ported to api-service).

Source: services/admin-service/src/schemas/user_management.py
Rewrites: AdminBaseResponse -> BaseResponse; import paths -> api_service.*
CLAUDE.md user identity rule: response schemas use user_uid: str (no user_id: int).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from api_service.common.schemas import BaseResponse, DateTimeModel
from api_service.common.utils.password_policy import check_password_strength


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

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        ok, message = check_password_strength(value)
        if not ok:
            raise ValueError(message)
        return value


class TopupUserRequest(BaseModel):
    amount: int = Field(
        ...,
        gt=0,
        le=10_000_000_000,
        description="充值金额（微元，1元=1,000,000微元）",
    )
    remark: str = Field(default="", max_length=255, description="备注")


class AdjustUserBalanceRequest(BaseModel):
    amount: int = Field(
        ...,
        ge=-10_000_000_000,
        le=10_000_000_000,
        description="正数增加余额，负数扣减余额（微元，1元=1,000,000微元）",
    )
    remark: str = Field(..., min_length=1, max_length=255, description="备注")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount must not be 0")
        return v


class UpdateUserRpmRequest(BaseModel):
    """Set or clear the per-user RPM override."""

    rpm_limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100_000,
        description="每分钟请求上限；留空清除覆盖、使用全局默认",
    )
    remark: str = Field(default="", max_length=255, description="备注（写入审计日志）")


# --- Response schemas ---


class UserListItem(DateTimeModel):
    uid: str
    email: str
    status: int
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    balance: int = 0
    rpm_limit: Optional[int] = None
    created_at: datetime

    @field_validator("uid", mode="before")
    @classmethod
    def stringify_uid(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value)


class UserListResponse(BaseResponse):
    data: Optional[dict] = None


class UserDetailData(DateTimeModel):
    uid: str
    email: str
    status: int
    email_verified_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    balance: int = 0
    frozen_amount: int = 0
    used_amount: int = 0
    total_requests: int = 0
    total_tokens: int = 0
    rpm_limit: Optional[int] = None
    default_rpm: int = 0
    current_tpm: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("uid", mode="before")
    @classmethod
    def stringify_uid(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value)


class UserDetailResponse(BaseResponse):
    data: Optional[UserDetailData] = None


class UserApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int = 0
    quota_limit: int = 0
    quota_used: int = 0
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime


class UserApiKeyListResponse(BaseResponse):
    data: Optional[list[UserApiKeyItem]] = None


class UserTransactionItem(DateTimeModel):
    id: int
    type: int
    amount: int
    balance_before: int = 0
    balance_after: int = 0
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    remark: Optional[str] = None
    operator_id: Optional[str] = None
    created_at: datetime


class UserTransactionListResponse(BaseResponse):
    data: Optional[dict] = None


class UserUsageLogItem(DateTimeModel):
    id: int
    request_id: str
    api_key_id: Optional[int] = None
    api_key_name: Optional[str] = None
    model_name: str
    selected_model: Optional[str] = None
    provider_slug: Optional[str] = None
    upstream_model: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cost: int = 0
    status: Optional[int] = None
    duration_ms: Optional[int] = None
    is_stream: bool = False
    config_version: Optional[int] = None
    config_source: Optional[str] = None
    inference_config_version: Optional[int] = None
    inference_config_source: Optional[str] = None
    routing_tier: Optional[int] = None
    score_source: Optional[str] = None
    router_trace_id: Optional[str] = None
    inference_error_code: Optional[str] = None
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    ip: Optional[str] = None
    cost_detail: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class UserUsageLogListResponse(BaseResponse):
    data: Optional[dict] = None


class UserUsageStatItem(DateTimeModel):
    id: int
    api_key_id: Optional[int] = None
    model_name: str
    stat_hour: datetime
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    total_cost: int = 0


class UserUsageStatListResponse(BaseResponse):
    data: Optional[list[UserUsageStatItem]] = None


class UserOperationResponse(BaseResponse):
    pass


# --- Usage analytics schemas ---


class UserUsageAnalyticsOverview(BaseModel):
    total_requests: int = 0
    success_requests: int = 0
    success_rate: float = 0.0
    total_cost: int = 0


class UserUsageAnalyticsModel(BaseModel):
    effective_model: str
    request_count: int = 0
    request_share: float = 0.0
    total_cost: int = 0


class UserUsageAnalyticsBucketCost(BaseModel):
    effective_model: str
    total_cost: int = 0


class UserUsageAnalyticsBucket(DateTimeModel):
    bucket_start: datetime
    label: str
    costs: list[UserUsageAnalyticsBucketCost] = []


class UserUsageAnalyticsData(DateTimeModel):
    range: Optional[str] = None
    granularity: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    currency: str = "micro_yuan"
    overview: Optional[UserUsageAnalyticsOverview] = None
    models: list[UserUsageAnalyticsModel] = []
    buckets: list[UserUsageAnalyticsBucket] = []


class UserUsageAnalyticsResponse(BaseResponse):
    data: Optional[UserUsageAnalyticsData] = None
