"""Admin authentication schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from admin_service.schemas.common import AdminBaseResponse, DateTimeModel
from admin_service.utils.password import check_password_strength


class AdminLoginRequest(BaseModel):
    """Admin login request."""

    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., description="密码")


class AdminUserData(BaseModel):
    """Admin data nested in login responses."""

    uid: int = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: str = Field(..., description="角色")


class AdminLoginResponseData(BaseModel):
    """Admin login response payload."""

    user: AdminUserData = Field(..., description="管理员信息")
    access_token: Optional[str] = Field(default=None, description="访问令牌")
    expires_in: Optional[int] = Field(default=None, description="访问令牌有效期（秒）")


class AdminLoginResponse(AdminBaseResponse):
    """Admin login response."""

    data: Optional[AdminLoginResponseData] = None


class AdminInfoResponseData(DateTimeModel):
    """Current admin profile response payload."""

    uid: int = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: str = Field(..., description="角色")
    status: int = Field(..., description="状态：0=禁用 1=正常")
    last_login_at: Optional[datetime] = Field(default=None, description="最近登录时间")
    created_at: datetime = Field(..., description="创建时间")


class AdminInfoResponse(AdminBaseResponse):
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


class AdminChangePasswordResponse(AdminBaseResponse):
    """Admin password change response."""


class AdminRefreshResponseData(BaseModel):
    """Admin refresh response payload."""

    access_token: str = Field(..., description="新的访问令牌")
    expires_in: int = Field(..., description="访问令牌有效期（秒）")


class AdminRefreshResponse(AdminBaseResponse):
    """Admin refresh response."""

    data: Optional[AdminRefreshResponseData] = None


class AdminLogoutResponse(AdminBaseResponse):
    """Admin logout response."""
