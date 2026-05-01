"""Schemas for internal voucher endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InternalVoucherGenerateRequest(BaseModel):
    amount: int = Field(gt=0)
    count: int = Field(ge=1, le=1000)
    starts_at: datetime
    expires_at: datetime
    operator_uid: str | None = None
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("starts_at", "expires_at", mode="after")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        from common.utils.timezone import to_shanghai_naive

        return to_shanghai_naive(value)


class InternalVoucherDisableRequest(BaseModel):
    operator_uid: str | None = None


class InternalVoucherItem(BaseModel):
    id: int
    code_prefix: str
    code_suffix: str
    amount: int
    status: int
    starts_at: datetime
    expires_at: datetime
    redeemed_user_uid: str | None = None
    redeemed_at: datetime | None = None
    created_by_admin_uid: str | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalCreatedVoucherItem(InternalVoucherItem):
    code: str


class InternalVoucherCreateResponse(BaseModel):
    items: list[InternalCreatedVoucherItem]


class InternalVoucherListResponse(BaseModel):
    items: list[InternalVoucherItem]
    total: int
    page: int
    page_size: int
