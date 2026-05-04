"""Admin voucher redemption-code management schemas."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse


class GenerateVoucherCodesRequest(BaseModel):
    amount: int = Field(
        ...,
        gt=0,
        le=10_000_000_000,
        description="Voucher amount (微元，1元=1,000,000微元)",
    )
    count: int = Field(..., ge=1, le=1000, description="Number of codes to generate")
    starts_at: datetime = Field(..., description="Validity start")
    expires_at: datetime = Field(..., description="Validity end")
    remark: str | None = Field(default=None, max_length=255, description="Admin note")

    @field_validator("starts_at", "expires_at", mode="after")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        from common.utils.timezone import to_shanghai_naive

        return to_shanghai_naive(value)

    @model_validator(mode="after")
    def validate_window(self):
        if self.starts_at >= self.expires_at:
            raise ValueError("starts_at must be earlier than expires_at")
        from common.utils.timezone import now as tz_now

        if self.starts_at < tz_now() - timedelta(days=1):
            raise ValueError("starts_at must not be more than 1 day in the past")
        return self


class VoucherCodeItem(DateTimeModel):
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


class CreatedVoucherCodeItem(VoucherCodeItem):
    code: str


class VoucherCodeCreateData(BaseModel):
    items: list[CreatedVoucherCodeItem]


class VoucherCodeCreateResponse(AdminBaseResponse):
    data: VoucherCodeCreateData | None = None


class VoucherCodeResponse(AdminBaseResponse):
    data: VoucherCodeItem | None = None


class VoucherCodeListResponse(AdminBaseResponse):
    data: PaginatedResponse[VoucherCodeItem] | None = None


class VoucherOperationResponse(AdminBaseResponse):
    pass
