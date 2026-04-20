"""User service Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)

from common.utils.timezone import format_iso
from user_service.utils.api_key_policy import normalize_allow_ips, normalize_allowed_models
from user_service.utils.email import normalize_email
from user_service.utils.password import check_password_strength

T = TypeVar("T")


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


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class BalanceResponseData(BaseModel):
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int

    @computed_field
    @property
    def available_balance(self) -> int:
        return self.balance - self.frozen_amount


class BalanceTransactionItem(DateTimeModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TopupOrderItem(DateTimeModel):
    id: int
    order_no: str
    amount: int
    status: int
    payment_channel: str
    payment_no: Optional[str] = None
    paid_at: Optional[datetime] = None
    remark: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminTopupOrderItem(TopupOrderItem):
    user_id: int
    operator_id: Optional[int] = None


class UsageStatItem(DateTimeModel):
    id: int
    api_key_id: Optional[int] = None
    model_name: str
    stat_hour: datetime
    request_count: int
    success_count: int
    error_count: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    total_cost: int

    model_config = ConfigDict(from_attributes=True)


class AdminUsageStatItem(UsageStatItem):
    user_id: int


class ApiCallLogItem(DateTimeModel):
    id: int
    request_id: str
    api_key_id: Optional[int] = None
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost: int
    status: int
    duration_ms: Optional[int] = None
    is_stream: bool
    error_code: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminApiCallLogItem(ApiCallLogItem):
    user_id: int
    ip: Optional[str] = None
    cost_detail: Optional[dict[str, Any]] = None


class ApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    quota_mode: int = Field(default=1, ge=1, le=2)
    quota_limit: int = Field(default=0, ge=0)
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("allowed_models")
    @classmethod
    def normalize_allowed_models_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allowed_models(value)

    @field_validator("allow_ips")
    @classmethod
    def normalize_allow_ips_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allow_ips(value)


class ApiKeyCreateData(BaseModel):
    key: str
    item: ApiKeyItem


class ApiKeyUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    quota_limit: Optional[int] = Field(default=None, gt=0)
    reset_quota_used: bool = False
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("allowed_models")
    @classmethod
    def normalize_allowed_models_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allowed_models(value)

    @field_validator("allow_ips")
    @classmethod
    def normalize_allow_ips_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allow_ips(value)


class AdminTopupRequest(BaseModel):
    amount: int = Field(..., gt=0)
    remark: str = Field(default="")


class AdminAdjustBalanceRequest(BaseModel):
    amount: int = Field(..., description="正数增加余额，负数扣减余额")
    remark: str = Field(..., min_length=1, max_length=255)


class RegisterRequest(BaseModel):
    """User registration request."""

    invitation_code: str = Field(..., min_length=1, max_length=64, description="Invitation code")
    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., min_length=8, max_length=128, description="Password")
    confirm_password: str = Field(..., description="Confirm password")
    verification_code: str = Field(..., min_length=6, max_length=6, description="Email verification code")
    lang: str = Field(default="zh", description="Language code")

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

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


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

    @model_validator(mode="after")
    def validate_new_password(self):
        ok, message = check_password_strength(self.new_password, lang=self.lang)
        if not ok:
            raise ValueError(message)
        return self


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
    purpose: Literal["register", "reset_password", "login", "verify"] = Field(
        default="register",
        description="register/reset_password/login/verify",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class VerifyEmailRequest(BaseModel):
    """Verify email request."""

    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class LoginWithCodeRequest(BaseModel):
    """Login with email code request."""

    email: EmailStr = Field(..., description="Login email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    """Reset password request."""

    email: EmailStr = Field(..., description="Email")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    lang: str = Field(default="zh", description="Language code")

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
