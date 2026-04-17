"""User service Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_serializer

from common.utils.timezone import format_iso
from user_service.utils.password import check_password_strength


class DateTimeModel(BaseModel):
    """Serialize datetimes as ISO strings."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AuthBaseResponse(BaseModel):
    """Base API response."""

    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")


class AuthErrorResponse(AuthBaseResponse):
    """Error API response."""

    code: int = Field(default=400, description="Status code")
    message: str = Field(default="error", description="Message")


class RegisterRequest(BaseModel):
    """User registration request."""

    invitation_code: str = Field(..., min_length=1, max_length=64, description="Invitation code")
    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., min_length=8, max_length=128, description="Password")
    confirm_password: str = Field(..., description="Confirm password")
    verification_code: str = Field(..., min_length=6, max_length=6, description="Email verification code")
    lang: str = Field(default="zh", description="Language code")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str, info) -> str:
        lang = info.data.get("lang", "zh")
        ok, message = check_password_strength(value, lang=lang)
        if not ok:
            raise ValueError(message)
        return value

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 6:
            raise ValueError("Verification code must be 6 digits")
        return value

    @field_validator("confirm_password")
    @classmethod
    def validate_password_match(cls, value: str, info) -> str:
        if "password" in info.data and value != info.data["password"]:
            raise ValueError("Passwords do not match")
        return value


class RegisterResponseData(DateTimeModel):
    """Registration payload."""

    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    created_at: datetime = Field(..., description="Created at")
    access_token: Optional[str] = Field(default=None, description="Access token")
    expires_in: Optional[int] = Field(default=None, description="Access token expiry seconds")


class RegisterResponse(AuthBaseResponse):
    """Registration response."""

    data: Optional[RegisterResponseData] = None


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., description="Password")


class UserData(DateTimeModel):
    """Embedded user payload for login responses."""

    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    status: int = Field(..., description="Status")
    email_verified_at: Optional[datetime] = Field(default=None, description="Email verified at")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login at")
    created_at: datetime = Field(..., description="Created at")


class LoginResponseData(BaseModel):
    """Login payload."""

    user: UserData = Field(..., description="User info")
    access_token: Optional[str] = Field(default=None, description="Access token")
    expires_in: Optional[int] = Field(default=None, description="Access token expiry seconds")


class LoginResponse(AuthBaseResponse):
    """Login response."""

    data: Optional[LoginResponseData] = None


class UserInfoResponseData(DateTimeModel):
    """Current user payload."""

    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    status: int = Field(..., description="Status")
    email_verified_at: Optional[datetime] = Field(default=None, description="Email verified at")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login at")
    created_at: datetime = Field(..., description="Created at")


class UserInfoResponse(AuthBaseResponse):
    """Current user response."""

    data: Optional[UserInfoResponseData] = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    old_password: str = Field(..., description="Old password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    lang: str = Field(default="zh", description="Language code")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str, info) -> str:
        lang = info.data.get("lang", "zh")
        ok, message = check_password_strength(value, lang=lang)
        if not ok:
            raise ValueError(message)
        return value


class ChangePasswordResponse(AuthBaseResponse):
    """Change password response."""


class RefreshResponseData(BaseModel):
    """Refresh token payload."""

    access_token: str = Field(..., description="New access token")
    refresh_token: Optional[str] = Field(default=None, description="New refresh token")
    expires_in: int = Field(..., description="Access token expiry seconds")


class RefreshResponse(AuthBaseResponse):
    """Refresh token response."""

    data: Optional[RefreshResponseData] = None


class LogoutResponse(AuthBaseResponse):
    """Logout response."""


class SendEmailCodeRequest(BaseModel):
    """Send email code request."""

    email: EmailStr = Field(..., description="Email")
    purpose: str = Field(default="register", description="register/reset_password/login")


class VerifyEmailRequest(BaseModel):
    """Verify email request."""

    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")


class LoginWithCodeRequest(BaseModel):
    """Login with email code request."""

    email: EmailStr = Field(..., description="Login email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")


class ResetPasswordRequest(BaseModel):
    """Reset password request."""

    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    lang: str = Field(default="zh", description="Language code")

    @field_validator("new_password")
    @classmethod
    def validate_reset_password(cls, value: str, info) -> str:
        lang = info.data.get("lang", "zh")
        ok, message = check_password_strength(value, lang=lang)
        if not ok:
            raise ValueError(message)
        return value


class RouterApiKeyItem(DateTimeModel):
    """Router API key item."""

    id: int = Field(..., description="Primary key id")
    name: str = Field(..., description="Display name")
    token_preview: str = Field(..., description="Masked key preview")
    is_active: bool = Field(..., description="Whether the key is active")
    is_deleted: bool = Field(default=False, description="Whether the key is deleted")
    billing_mode: str = Field(..., description="Billing mode")
    balance: Optional[float] = Field(default=None, description="Prepaid balance")
    daily_quota_tokens: Optional[int] = Field(default=None, description="Daily token quota")
    monthly_quota_tokens: Optional[int] = Field(default=None, description="Monthly token quota")
    daily_quota_cost: Optional[float] = Field(default=None, description="Daily cost quota")
    monthly_quota_cost: Optional[float] = Field(default=None, description="Monthly cost quota")
    rate_limit_rpm: Optional[int] = Field(default=None, description="RPM limit")
    last_used_at: Optional[datetime] = Field(default=None, description="Last used at")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")


class RouterApiKeyCreateRequest(BaseModel):
    """Create router API key request."""

    name: str = Field(..., min_length=1, max_length=100, description="Key name")


class RouterApiKeyUpdateRequest(BaseModel):
    """Update router API key request."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Key name")
    is_active: Optional[bool] = Field(default=None, description="Whether active")


class RouterApiKeyListResponseData(BaseModel):
    """Router API key list payload."""

    items: list[RouterApiKeyItem] = Field(default_factory=list, description="Owned API keys")


class RouterApiKeyListResponse(AuthBaseResponse):
    """Router API key list response."""

    data: Optional[RouterApiKeyListResponseData] = None


class RouterApiKeyCreateResponseData(BaseModel):
    """Router API key create payload."""

    item: RouterApiKeyItem = Field(..., description="Created API key metadata")
    api_key: str = Field(..., description="Raw API key returned once")


class RouterApiKeyCreateResponse(AuthBaseResponse):
    """Router API key create response."""

    data: Optional[RouterApiKeyCreateResponseData] = None


class RouterApiKeyUpdateResponse(AuthBaseResponse):
    """Router API key update response."""

    data: Optional[RouterApiKeyItem] = None


class RouterApiKeyRevealResponseData(BaseModel):
    """Router API key reveal payload."""

    item: RouterApiKeyItem = Field(..., description="API key metadata")
    api_key: str = Field(..., description="Raw API key")


class RouterApiKeyRevealResponse(AuthBaseResponse):
    """Router API key reveal response."""

    data: Optional[RouterApiKeyRevealResponseData] = None


class RouterApiKeyDeleteResponseData(BaseModel):
    """Router API key delete payload."""

    deleted: bool = Field(..., description="Whether the key is deactivated")


class RouterApiKeyDeleteResponse(AuthBaseResponse):
    """Router API key delete response."""

    data: Optional[RouterApiKeyDeleteResponseData] = None
