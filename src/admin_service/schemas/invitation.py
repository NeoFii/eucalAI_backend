"""Admin invitation-code schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from admin_service.schemas.common import AdminBaseResponse, DateTimeModel


class GenerateInvitationCodeRequest(BaseModel):
    """Generate invitation-code request."""

    quantity: int = Field(default=1, ge=1, le=100, description="生成数量")
    expires_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="过期天数（与 expires_at 二选一）",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="具体过期时间（与 expires_days 二选一，优先使用）",
    )
    max_uses: int = Field(default=1, ge=1, description="每个码最大使用次数")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")


class InvitationCodeData(DateTimeModel):
    """Invitation-code response item."""

    id: int = Field(..., description="邀请码ID")
    code: str = Field(..., description="邀请码")
    status: int = Field(..., description="状态：0=未使用 1=已使用 2=已弃用")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    used_by: Optional[int] = Field(default=None, description="使用者UID")
    used_at: Optional[datetime] = Field(default=None, description="使用时间")
    remark: Optional[str] = Field(default=None, description="备注")
    created_at: datetime = Field(..., description="创建时间")


class GenerateInvitationCodeResponseData(BaseModel):
    """Generate invitation-code response payload."""

    codes: list[InvitationCodeData] = Field(..., description="生成的邀请码列表")


class GenerateInvitationCodeResponse(AdminBaseResponse):
    """Generate invitation-code response."""

    data: Optional[GenerateInvitationCodeResponseData] = None


class InvitationCodeListItem(DateTimeModel):
    """Invitation-code list item."""

    id: int = Field(..., description="邀请码ID")
    code: str = Field(..., description="邀请码")
    status: int = Field(..., description="状态：0=未使用 1=已使用 2=已弃用")
    created_by: Optional[int] = Field(default=None, description="创建者ID")
    used_by: Optional[int] = Field(default=None, description="使用者UID")
    used_at: Optional[datetime] = Field(default=None, description="使用时间")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    remark: Optional[str] = Field(default=None, description="备注")
    created_at: datetime = Field(..., description="创建时间")


class InvitationCodeListResponseData(BaseModel):
    """Invitation-code list response payload."""

    items: list[InvitationCodeListItem] = Field(..., description="邀请码列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class InvitationCodeListResponse(AdminBaseResponse):
    """Invitation-code list response."""

    data: Optional[InvitationCodeListResponseData] = None


class UpdateInvitationCodeRequest(BaseModel):
    """Update invitation-code request."""

    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")


class EnableInvitationCodeRequest(BaseModel):
    """Enable invitation-code request."""

    code_id: int = Field(..., description="邀请码ID")


class DisableInvitationCodeRequest(BaseModel):
    """Disable invitation-code request."""

    code_id: int = Field(..., description="邀请码ID")


class InvitationCodeOperationResponse(AdminBaseResponse):
    """Invitation-code operation response."""


class DashboardStatsResponseData(BaseModel):
    """Dashboard stats response payload."""

    total_users: int = Field(default=0, description="总用户数")
    total_invitation_codes: int = Field(default=0, description="总邀请码数")
    used_invitation_codes: int = Field(default=0, description="已使用邀请码数")
    valid_invitation_codes: int = Field(default=0, description="有效邀请码数")


class DashboardStatsResponse(AdminBaseResponse):
    """Dashboard stats response."""

    data: Optional[DashboardStatsResponseData] = None
