"""Schemas for internal user management endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.config import settings


class InternalUserListItem(BaseModel):
    uid: str
    email: str
    status: int
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    balance: int
    rpm_limit: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalUserListResponse(BaseModel):
    items: list[InternalUserListItem]
    total: int
    page: int
    page_size: int


class InternalUserDetailResponse(BaseModel):
    uid: str
    email: str
    status: int
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int
    rpm_limit: int | None = None
    default_rpm: int
    current_tpm: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalUpdateStatusRequest(BaseModel):
    status: Literal[0, 1]


class InternalUpdateStatusResponse(BaseModel):
    uid: str
    before_status: int
    after_status: int


class InternalResetPasswordRequest(BaseModel):
    new_password: str


class InternalTopupRequest(BaseModel):
    amount: int = Field(gt=0, le=settings.MAX_TOPUP_AMOUNT)
    operator_uid: str
    remark: str = Field(default="", max_length=255)


class InternalAdjustBalanceRequest(BaseModel):
    amount: int = Field(ge=-settings.MAX_TOPUP_AMOUNT, le=settings.MAX_TOPUP_AMOUNT)
    operator_uid: str
    remark: str = Field(max_length=255)


class InternalUpdateRpmRequest(BaseModel):
    """Set or clear the per-user RPM override.

    `rpm_limit=None` clears the override so the user falls back to
    `Settings.DEFAULT_USER_RPM`. Concrete values must be >= 1.
    """

    rpm_limit: int | None = Field(default=None, ge=1, le=100_000)
    operator_uid: str
    remark: str = Field(default="", max_length=255)


class InternalTransactionItem(BaseModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: str | None = None
    ref_id: str | None = None
    remark: str | None = None
    operator_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalTransactionListResponse(BaseModel):
    items: list[InternalTransactionItem]
    total: int
    page: int
    page_size: int


class InternalApiKeyItem(BaseModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: str | None = None
    allow_ips: str | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)