"""Auth schema split for user-service."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from user_service.schemas.common import AuthBaseResponse, DateTimeModel
from user_service.utils.email import normalize_email
from user_service.utils.password import check_password_strength


class RegisterRequest(BaseModel):
    """User registration request."""

    invitation_code: str = Field(..., min_length=1, max_length=64, description="Invitation code")
    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., min_length=8, max_length=72, description="Password")
    confirm_password: str = Field(..., description="Confirm password")
    verification_code: str = Field(..., min_length=6, max_length=6, description="Email verification code")
    lang: Literal["zh", "en"] = Field(default="zh", description="Language code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)

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

    @model_validator(mode="after")
    def validate_password_strength(self):
        ok, message = check_password_strength(self.password, lang=self.lang)
        if not ok:
            raise ValueError(message)
        return self


class RegisterResponseData(DateTimeModel):
    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    created_at: datetime = Field(..., description="Created at")
    access_token: Optional[str] = Field(default=None, description="Access token")
    expires_in: Optional[int] = Field(default=None, description="Access token expiry seconds")


class RegisterResponse(AuthBaseResponse):
    data: Optional[RegisterResponseData] = None


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., min_length=1, max_length=72, description="Password")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72-byte bcrypt limit")
        return value


class UserData(DateTimeModel):
    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    status: int = Field(..., description="Status")
    email_verified_at: Optional[datetime] = Field(default=None, description="Email verified at")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login at")
    created_at: datetime = Field(..., description="Created at")


class LoginResponseData(BaseModel):
    user: UserData = Field(..., description="User info")
    access_token: Optional[str] = Field(default=None, description="Access token")
    expires_in: Optional[int] = Field(default=None, description="Access token expiry seconds")


class LoginResponse(AuthBaseResponse):
    data: Optional[LoginResponseData] = None


class UserInfoResponseData(DateTimeModel):
    uid: int = Field(..., description="User UID")
    email: str = Field(..., description="Email")
    status: int = Field(..., description="Status")
    email_verified_at: Optional[datetime] = Field(default=None, description="Email verified at")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login at")
    created_at: datetime = Field(..., description="Created at")


class UserInfoResponse(AuthBaseResponse):
    data: Optional[UserInfoResponseData] = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., max_length=72, description="Old password")
    new_password: str = Field(..., min_length=8, max_length=72, description="New password")
    lang: Literal["zh", "en"] = Field(default="zh", description="Language code")

    @model_validator(mode="after")
    def validate_new_password(self):
        ok, message = check_password_strength(self.new_password, lang=self.lang)
        if not ok:
            raise ValueError(message)
        return self


class ChangePasswordResponse(AuthBaseResponse):
    """Change password response."""


class RefreshResponseData(BaseModel):
    access_token: str = Field(..., description="New access token")
    refresh_token: Optional[str] = Field(default=None, description="New refresh token")
    expires_in: int = Field(..., description="Access token expiry seconds")


class RefreshResponse(AuthBaseResponse):
    data: Optional[RefreshResponseData] = None


class LogoutResponse(AuthBaseResponse):
    """Logout response."""


class SendEmailCodeRequest(BaseModel):
    email: EmailStr = Field(..., description="Email")
    purpose: Literal["register", "reset_password", "login", "verify"] = Field(
        default="register",
        description="register/reset_password/login/verify",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class VerifyEmailRequest(BaseModel):
    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class LoginWithCodeRequest(BaseModel):
    email: EmailStr = Field(..., description="Login email")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit code")
    new_password: str = Field(..., min_length=8, max_length=72, description="New password")
    lang: Literal["zh", "en"] = Field(default="zh", description="Language code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)

    @model_validator(mode="after")
    def validate_reset_password(self):
        ok, message = check_password_strength(self.new_password, lang=self.lang)
        if not ok:
            raise ValueError(message)
        return self


__all__ = [
    "ChangePasswordRequest",
    "ChangePasswordResponse",
    "LoginRequest",
    "LoginResponse",
    "LoginResponseData",
    "LoginWithCodeRequest",
    "LogoutResponse",
    "RefreshResponse",
    "RefreshResponseData",
    "RegisterRequest",
    "RegisterResponse",
    "RegisterResponseData",
    "ResetPasswordRequest",
    "SendEmailCodeRequest",
    "UserData",
    "UserInfoResponse",
    "UserInfoResponseData",
    "VerifyEmailRequest",
]
