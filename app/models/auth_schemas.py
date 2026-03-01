"""
认证相关 Pydantic 模型
定义请求和响应的数据结构
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.password import check_password_strength


# ==================== 基础响应模型 ====================

class AuthBaseResponse(BaseModel):
    """认证基础响应"""
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")


class AuthErrorResponse(AuthBaseResponse):
    """认证错误响应"""
    code: int = Field(default=400, description="错误码")
    message: str = Field(default="error", description="错误消息")


# ==================== 用户注册 ====================

class RegisterRequest(BaseModel):
    """用户注册请求"""
    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    confirm_password: str = Field(..., description="确认密码")
    verification_code: str = Field(..., min_length=6, max_length=6, description="邮箱验证码")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """验证密码强度"""
        ok, msg = check_password_strength(v)
        if not ok:
            raise ValueError(msg)
        return v

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, v: str) -> str:
        """验证验证码格式"""
        if not v.isdigit() or len(v) != 6:
            raise ValueError("验证码必须是6位数字")
        return v

    @field_validator("confirm_password")
    @classmethod
    def validate_password_match(cls, v: str, info) -> str:
        """验证两次密码一致"""
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("两次输入的密码不一致")
        return v


class RegisterResponseData(BaseModel):
    """注册响应数据"""
    uid: int = Field(..., description="用户唯一ID")
    email: str = Field(..., description="注册邮箱")
    nickname: Optional[str] = Field(default=None, description="昵称")
    created_at: datetime = Field(..., description="注册时间")
    access_token: Optional[str] = Field(default=None, description="访问令牌")
    refresh_token: Optional[str] = Field(default=None, description="刷新令牌")
    expires_in: Optional[int] = Field(default=None, description="访问令牌有效期（秒）")


class RegisterResponse(AuthBaseResponse):
    """用户注册响应"""
    data: Optional[RegisterResponseData] = None


# ==================== 用户登录 ====================

class LoginRequest(BaseModel):
    """用户登录请求"""
    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., description="密码")


class LoginResponseData(BaseModel):
    """登录响应数据"""
    uid: int = Field(..., description="用户唯一ID")
    email: str = Field(..., description="邮箱")
    nickname: Optional[str] = Field(default=None, description="昵称")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    access_token: Optional[str] = Field(default=None, description="访问令牌")
    refresh_token: Optional[str] = Field(default=None, description="刷新令牌")
    expires_in: Optional[int] = Field(default=None, description="访问令牌有效期（秒）")


class LoginResponse(AuthBaseResponse):
    """用户登录响应"""
    data: Optional[LoginResponseData] = None


# ==================== 当前用户信息 ====================

class UserInfoResponseData(BaseModel):
    """用户信息响应数据"""
    uid: int = Field(..., description="用户唯一ID")
    email: str = Field(..., description="邮箱")
    nickname: Optional[str] = Field(default=None, description="昵称")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    status: int = Field(..., description="状态：0=禁用 1=正常 2=待验证")
    email_verified_at: Optional[datetime] = Field(default=None, description="邮箱验证时间")
    last_login_at: Optional[datetime] = Field(default=None, description="最近登录时间")
    created_at: datetime = Field(..., description="注册时间")


class UserInfoResponse(AuthBaseResponse):
    """获取用户信息响应"""
    data: Optional[UserInfoResponseData] = None


# ==================== 修改密码 ====================

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """验证新密码强度"""
        ok, msg = check_password_strength(v)
        if not ok:
            raise ValueError(msg)
        return v


class ChangePasswordResponse(AuthBaseResponse):
    """修改密码响应"""
    pass


# ==================== Token 刷新 ====================

class RefreshResponseData(BaseModel):
    """刷新 Token 响应数据"""
    access_token: str = Field(..., description="新的访问令牌")
    refresh_token: Optional[str] = Field(default=None, description="新的刷新令牌（可选）")
    expires_in: int = Field(..., description="访问令牌有效期（秒）")


class RefreshResponse(AuthBaseResponse):
    """刷新 Token 响应"""
    data: Optional[RefreshResponseData] = None


# ==================== 登出 ====================

class LogoutResponse(AuthBaseResponse):
    """登出响应"""
    pass


# ==================== 邮箱验证（预留）====================

class SendEmailCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    purpose: str = Field(default="register", description="用途：register/reset_password")


class VerifyEmailRequest(BaseModel):
    """验证邮箱请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    code: str = Field(..., min_length=6, max_length=6, description="6位验证码")


# ==================== 邮箱验证码登录 ====================

class LoginWithCodeRequest(BaseModel):
    """邮箱验证码登录请求"""
    email: EmailStr = Field(..., description="登录邮箱")
    code: str = Field(..., min_length=6, max_length=6, description="6位验证码")


# ==================== 忘记密码 ====================

class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    code: str = Field(..., min_length=6, max_length=6, description="6位验证码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """验证新密码强度"""
        ok, msg = check_password_strength(v)
        if not ok:
            raise ValueError(msg)
        return v
