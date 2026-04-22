"""Admin voucher management schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from admin_service.schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse


class CreateVoucherRequest(BaseModel):
    uid: int = Field(..., description="Target user UID")
    amount: int = Field(..., gt=0, description="Voucher amount (fen)")
    expires_at: datetime | None = Field(default=None, description="Expiration time")
    remark: str | None = Field(default=None, max_length=255, description="Admin note")


class UpdateVoucherRequest(BaseModel):
    status: int | None = Field(default=None, description="1=active 2=disabled")
    expires_at: datetime | None = Field(default=None, description="Expiration time")
    remark: str | None = Field(default=None, max_length=255, description="Admin note")


class VoucherItem(DateTimeModel):
    id: int
    user_id: int
    status: int
    original_amount: int
    remaining_amount: int
    frozen_amount: int
    used_amount: int
    expires_at: datetime | None = None
    created_by_admin_uid: int | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime


class VoucherResponse(AdminBaseResponse):
    data: VoucherItem | None = None


class VoucherListResponse(AdminBaseResponse):
    data: PaginatedResponse[VoucherItem] | None = None


class VoucherOperationResponse(AdminBaseResponse):
    pass
