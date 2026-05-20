"""Admin account management schemas (admin-on-admin CRUD).

Ported from `services/admin-service/src/schemas/admin_user.py`. Used by the
Plan 05-02 admin_users controller; Task 2 ships the file with the schema
classes pre-defined so 05-02 can simply re-export them. Rewrites match the
admin/auth.py port.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from app.common.api.pagination import PaginatedResponse
from app.common.schemas import BaseResponse, DateTimeModel
from app.common.utils.password_policy import check_password_strength
from app.model.enums import AdminRole

_ROLE_INT_TO_STR = {AdminRole.ADMIN: "admin", AdminRole.SUPER_ADMIN: "super_admin"}
_ROLE_STR_TO_INT = {"admin": AdminRole.ADMIN, "super_admin": AdminRole.SUPER_ADMIN}


class AdminListItem(DateTimeModel):
    """Admin list item."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: int = Field(..., description="Admin role: 0=admin 1=super_admin")
    is_root: bool = Field(default=False, description="Root admin flag")
    status: int = Field(..., description="Admin status")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login time")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)

    @field_serializer("role")
    def serialize_role(self, value: int) -> str:
        return _ROLE_INT_TO_STR.get(value, "admin")


class AdminListResponse(BaseResponse):
    """Admin list response."""

    data: Optional[PaginatedResponse[AdminListItem]] = None


class CreateAdminRequest(BaseModel):
    """Create admin request."""

    email: EmailStr = Field(..., description="Admin email")
    name: str = Field(..., min_length=1, max_length=100, description="Admin name")
    password: str = Field(..., min_length=8, max_length=128, description="Admin password")
    role: int | str = Field(
        default=AdminRole.ADMIN,
        description="Admin role: 0/1 or 'admin'/'super_admin'",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        ok, message = check_password_strength(value)
        if not ok:
            raise ValueError(message)
        return value

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, value: int | str) -> int:
        if isinstance(value, str):
            if value not in _ROLE_STR_TO_INT:
                raise ValueError("role must be 'admin' or 'super_admin'")
            return _ROLE_STR_TO_INT[value]
        if value not in {AdminRole.ADMIN, AdminRole.SUPER_ADMIN}:
            raise ValueError("role must be 0 (admin) or 1 (super_admin)")
        return value


class CreateAdminResponseData(DateTimeModel):
    """Create admin response payload."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: int = Field(..., description="Admin role: 0=admin 1=super_admin")
    status: int = Field(..., description="Admin status")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)

    @field_serializer("role")
    def serialize_role(self, value: int) -> str:
        return _ROLE_INT_TO_STR.get(value, "admin")


class CreateAdminResponse(BaseResponse):
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


class UpdateAdminRoleRequest(BaseModel):
    """Update admin role request."""

    role: int | str = Field(..., description="Target role: 0/1 or 'admin'/'super_admin'")

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, value: int | str) -> int:
        if isinstance(value, str):
            if value not in _ROLE_STR_TO_INT:
                raise ValueError("role must be 'admin' or 'super_admin'")
            return _ROLE_STR_TO_INT[value]
        if value not in {AdminRole.ADMIN, AdminRole.SUPER_ADMIN}:
            raise ValueError("role must be 0 (admin) or 1 (super_admin)")
        return value


__all__ = [
    "AdminListItem",
    "AdminListResponse",
    "CreateAdminRequest",
    "CreateAdminResponse",
    "CreateAdminResponseData",
    "ResetAdminPasswordRequest",
    "UpdateAdminRoleRequest",
    "UpdateAdminStatusRequest",
]
