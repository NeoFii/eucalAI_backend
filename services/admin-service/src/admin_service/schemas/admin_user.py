"""Admin account management schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from common.api import PaginatedResponse
from admin_service.schemas.common import AdminBaseResponse, DateTimeModel
from admin_service.utils.password import check_password_strength


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


class AdminListResponse(AdminBaseResponse):
    """Admin list response."""

    data: Optional[PaginatedResponse[AdminListItem]] = None


class CreateAdminRequest(BaseModel):
    """Create admin request."""

    email: EmailStr = Field(..., description="Admin email")
    name: str = Field(..., min_length=1, max_length=100, description="Admin name")
    password: str = Field(..., min_length=8, max_length=128, description="Admin password")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        ok, message = check_password_strength(value)
        if not ok:
            raise ValueError(message)
        return value


class CreateAdminResponseData(DateTimeModel):
    """Create admin response payload."""

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
        ok, message = check_password_strength(value)
        if not ok:
            raise ValueError(message)
        return value
