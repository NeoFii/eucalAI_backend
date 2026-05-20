"""Admin authentication schemas.

Ported from `services/admin-service/src/schemas/auth.py` in Plan 05-01 /
Task 2. The source's flat-package imports (`schemas.common`, `core.enums`,
`utils.password`) are rewritten to their app namespace equivalents
(see the imports below). Per Pitfall 8, response classes inherit
`BaseResponse` (NOT the legacy per-domain envelope name).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from app.common.schemas import BaseResponse, DateTimeModel
from app.common.utils.password_policy import check_password_strength
from app.model.enums import AdminRole

_ROLE_INT_TO_STR = {AdminRole.ADMIN: "admin", AdminRole.SUPER_ADMIN: "super_admin"}


class AdminLoginRequest(BaseModel):
    """Admin login request."""

    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., max_length=128, description="密码")


class AdminUserData(BaseModel):
    """Admin data nested in login responses."""

    uid: str = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: int = Field(..., description="角色: 0=admin 1=super_admin")
    is_root: bool = Field(default=False, description="根管理员标记")

    @field_serializer("role")
    def serialize_role(self, value: int) -> str:
        return _ROLE_INT_TO_STR.get(value, "admin")


class AdminLoginResponseData(BaseModel):
    """Admin login response payload."""

    user: AdminUserData = Field(..., description="管理员信息")
    access_token: Optional[str] = Field(default=None, description="访问令牌")
    expires_in: Optional[int] = Field(default=None, description="访问令牌有效期（秒）")


class AdminLoginResponse(BaseResponse):
    """Admin login response."""

    data: Optional[AdminLoginResponseData] = None


class AdminInfoResponseData(DateTimeModel):
    """Current admin profile response payload."""

    uid: str = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: int = Field(..., description="角色: 0=admin 1=super_admin")
    is_root: bool = Field(default=False, description="根管理员标记")
    status: int = Field(..., description="状态：0=禁用 1=正常")
    last_login_at: Optional[datetime] = Field(default=None, description="最近登录时间")
    created_at: datetime = Field(..., description="创建时间")

    @field_serializer("role")
    def serialize_role(self, value: int) -> str:
        return _ROLE_INT_TO_STR.get(value, "admin")


class AdminInfoResponse(BaseResponse):
    """Current admin response."""

    data: Optional[AdminInfoResponseData] = None


class AdminChangePasswordRequest(BaseModel):
    """Admin password change request."""

    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        ok, message = check_password_strength(value)
        if not ok:
            raise ValueError(message)
        return value


class AdminChangePasswordResponse(BaseResponse):
    """Admin password change response."""


class AdminRefreshResponseData(BaseModel):
    """Admin refresh response payload."""

    access_token: str = Field(..., description="新的访问令牌")
    expires_in: int = Field(..., description="访问令牌有效期（秒）")


class AdminRefreshResponse(BaseResponse):
    """Admin refresh response."""

    data: Optional[AdminRefreshResponseData] = None


class AdminLogoutResponse(BaseResponse):
    """Admin logout response."""


__all__ = [
    "AdminChangePasswordRequest",
    "AdminChangePasswordResponse",
    "AdminInfoResponse",
    "AdminInfoResponseData",
    "AdminLoginRequest",
    "AdminLoginResponse",
    "AdminLoginResponseData",
    "AdminLogoutResponse",
    "AdminRefreshResponse",
    "AdminRefreshResponseData",
    "AdminUserData",
]
