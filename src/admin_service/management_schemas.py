"""Schemas for admin management endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from admin_service.schemas import AdminBaseResponse, DateTimeModel
from admin_service.utils.password import check_password_strength


AdminAuditCategory = Literal["all", "governance", "auth"]


class AdminListItem(DateTimeModel):
    """Admin list item."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: str = Field(..., description="Admin role")
    status: int = Field(..., description="Admin status")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login time")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)


class AdminListResponseData(BaseModel):
    """Admin list response data."""

    items: list[AdminListItem] = Field(..., description="Admin list")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")


class AdminListResponse(AdminBaseResponse):
    """Admin list response."""

    data: Optional[AdminListResponseData] = None


class CreateAdminRequest(BaseModel):
    """Create admin request."""

    email: EmailStr = Field(..., description="Admin email")
    name: str = Field(..., min_length=1, max_length=100, description="Admin name")
    password: str = Field(..., min_length=8, max_length=128, description="Admin password")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        ok, msg = check_password_strength(value)
        if not ok:
            raise ValueError(msg)
        return value


class CreateAdminResponseData(DateTimeModel):
    """Create admin response data."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: str = Field(..., description="Admin role")
    status: int = Field(..., description="Admin status")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)


class CreateAdminResponse(AdminBaseResponse):
    """Create admin response."""

    data: Optional[CreateAdminResponseData] = None


class UpdateAdminStatusRequest(BaseModel):
    """Update admin status request."""

    status: int = Field(..., description="Admin status")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: int) -> int:
        if value not in {0, 1}:
            raise ValueError("status must be 0 or 1")
        return value


class ResetAdminPasswordRequest(BaseModel):
    """Reset admin password request."""

    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        ok, msg = check_password_strength(value)
        if not ok:
            raise ValueError(msg)
        return value


class AdminAuditActor(BaseModel):
    """Admin summary embedded in audit log response."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: str = Field(..., description="Admin role")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)


class AdminAuditLogItem(DateTimeModel):
    """Admin audit log item."""

    id: int = Field(..., description="Audit log id")
    actor_admin: AdminAuditActor = Field(..., description="Actor admin")
    target_admin: Optional[AdminAuditActor] = Field(default=None, description="Target admin")
    action: str = Field(..., description="Audit action")
    resource_type: str = Field(..., description="Resource type")
    resource_id: Optional[str] = Field(default=None, description="Resource id")
    status: str = Field(..., description="success/failed")
    reason: Optional[str] = Field(default=None, description="Reason")
    ip_address: Optional[str] = Field(default=None, description="Source IP")
    user_agent: Optional[str] = Field(default=None, description="Source user agent")
    before_data: Optional[dict] = Field(default=None, description="Data before change")
    after_data: Optional[dict] = Field(default=None, description="Data after change")
    created_at: datetime = Field(..., description="Created at")


class AdminAuditLogListData(BaseModel):
    """Admin audit log list response data."""

    items: list[AdminAuditLogItem] = Field(..., description="Audit log list")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")


class AdminAuditLogListResponse(AdminBaseResponse):
    """Admin audit log list response."""

    data: Optional[AdminAuditLogListData] = None
