"""
管理员服务 Pydantic 模型
定义请求和响应的数据结构
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator, model_serializer

from admin_service.utils.password import check_password_strength
from common.utils.timezone import format_iso


# ==================== 基础响应模型 ====================

class AdminBaseResponse(BaseModel):
    """管理员基础响应"""
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")


class DateTimeModel(BaseModel):
    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AdminErrorResponse(AdminBaseResponse):
    """管理员错误响应"""
    code: int = Field(default=400, description="错误码")
    message: str = Field(default="error", description="错误消息")


# ==================== 管理员登录 ====================

class AdminLoginRequest(BaseModel):
    """管理员登录请求"""
    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., description="密码")


class AdminUserData(BaseModel):
    """管理员数据嵌套模型（登录响应使用）"""
    uid: int = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: str = Field(..., description="角色")


class AdminLoginResponseData(BaseModel):
    """管理员登录响应数据"""
    user: AdminUserData = Field(..., description="管理员信息")
    access_token: Optional[str] = Field(default=None, description="访问令牌")
    expires_in: Optional[int] = Field(default=None, description="访问令牌有效期（秒）")


class AdminLoginResponse(AdminBaseResponse):
    """管理员登录响应"""
    data: Optional[AdminLoginResponseData] = None


# ==================== 当前管理员信息 ====================

class AdminInfoResponseData(DateTimeModel):
    """管理员信息响应数据"""
    uid: int = Field(..., description="管理员唯一ID")
    email: str = Field(..., description="邮箱")
    name: str = Field(..., description="姓名")
    role: str = Field(..., description="角色")
    status: int = Field(..., description="状态：0=禁用 1=正常")
    last_login_at: Optional[datetime] = Field(default=None, description="最近登录时间")
    created_at: datetime = Field(..., description="创建时间")


class AdminInfoResponse(AdminBaseResponse):
    """获取管理员信息响应"""
    data: Optional[AdminInfoResponseData] = None


# ==================== 修改密码 ====================

class AdminChangePasswordRequest(BaseModel):
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


class AdminChangePasswordResponse(AdminBaseResponse):
    """修改密码响应"""
    pass


# ==================== Token 刷新 ====================

class AdminRefreshResponseData(BaseModel):
    """刷新 Token 响应数据"""
    access_token: str = Field(..., description="新的访问令牌")
    expires_in: int = Field(..., description="访问令牌有效期（秒）")


class AdminRefreshResponse(AdminBaseResponse):
    """刷新 Token 响应"""
    data: Optional[AdminRefreshResponseData] = None


# ==================== 登出 ====================

class AdminLogoutResponse(AdminBaseResponse):
    """登出响应"""
    pass


# ==================== 邀请码生成 ====================

class GenerateInvitationCodeRequest(BaseModel):
    """生成邀请码请求"""
    quantity: int = Field(default=1, ge=1, le=100, description="生成数量")
    expires_days: Optional[int] = Field(default=None, ge=1, le=365, description="过期天数（与 expires_at 二选一）")
    expires_at: Optional[datetime] = Field(default=None, description="具体过期时间（与 expires_days 二选一，优先使用）")
    max_uses: int = Field(default=1, ge=1, description="每个码最大使用次数")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")


class InvitationCodeData(DateTimeModel):
    """邀请码数据"""
    id: int = Field(..., description="邀请码ID")
    code: str = Field(..., description="邀请码")
    status: int = Field(..., description="状态：0=未使用 1=已使用 2=已弃用")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    used_by: Optional[int] = Field(default=None, description="使用者UID")
    used_at: Optional[datetime] = Field(default=None, description="使用时间")
    remark: Optional[str] = Field(default=None, description="备注")
    created_at: datetime = Field(..., description="创建时间")


class GenerateInvitationCodeResponseData(BaseModel):
    """生成邀请码响应数据"""
    codes: list[InvitationCodeData] = Field(..., description="生成的邀请码列表")


class GenerateInvitationCodeResponse(AdminBaseResponse):
    """生成邀请码响应"""
    data: Optional[GenerateInvitationCodeResponseData] = None


# ==================== 邀请码列表 ====================

class InvitationCodeListItem(DateTimeModel):
    """邀请码列表项"""
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
    """邀请码列表响应数据"""
    items: list[InvitationCodeListItem] = Field(..., description="邀请码列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class InvitationCodeListResponse(AdminBaseResponse):
    """邀请码列表响应"""
    data: Optional[InvitationCodeListResponseData] = None


# ==================== 邀请码操作 ====================

class UpdateInvitationCodeRequest(BaseModel):
    """更新邀请码请求"""
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")


class EnableInvitationCodeRequest(BaseModel):
    """启用邀请码请求"""
    code_id: int = Field(..., description="邀请码ID")


class DisableInvitationCodeRequest(BaseModel):
    """弃用邀请码请求"""
    code_id: int = Field(..., description="邀请码ID")


class InvitationCodeOperationResponse(AdminBaseResponse):
    """邀请码操作响应"""
    pass


# ==================== 仪表盘统计 ====================

class DashboardStatsResponseData(BaseModel):
    """仪表盘统计响应数据"""
    total_users: int = Field(default=0, description="总用户数")
    total_invitation_codes: int = Field(default=0, description="总邀请码数")
    used_invitation_codes: int = Field(default=0, description="已使用邀请码数")
    valid_invitation_codes: int = Field(default=0, description="有效邀请码数")


class DashboardStatsResponse(AdminBaseResponse):
    """仪表盘统计响应"""
    data: Optional[DashboardStatsResponseData] = None


# ==================== 管理员管理 (Management) ====================

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


