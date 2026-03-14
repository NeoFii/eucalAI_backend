"""
管理员服务 Pydantic 模型
定义请求和响应的数据结构
"""

from datetime import datetime
from typing import Optional

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


# ==================== 新闻管理 ====================

class CreateNewsRequest(BaseModel):
    """创建新闻请求"""
    title: str = Field(..., min_length=1, max_length=255, description="新闻标题")
    slug: str = Field(..., min_length=1, max_length=255, description="URL路径标识")
    language: str = Field(default="zh", description="语言: zh=中文 en=英文")
    summary: Optional[str] = Field(default=None, max_length=500, description="摘要")
    cover_image: Optional[str] = Field(default=None, max_length=500, description="封面图URL")
    content: str = Field(..., description="Markdown正文内容")
    status: int = Field(default=0, ge=0, le=2, description="状态：0=草稿 1=已发布 2=已下线")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")


class UpdateNewsRequest(BaseModel):
    """更新新闻请求"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255, description="新闻标题")
    slug: Optional[str] = Field(default=None, min_length=1, max_length=255, description="URL路径标识")
    language: Optional[str] = Field(default=None, description="语言: zh=中文 en=英文")
    summary: Optional[str] = Field(default=None, max_length=500, description="摘要")
    cover_image: Optional[str] = Field(default=None, max_length=500, description="封面图URL")
    content: Optional[str] = Field(default=None, description="Markdown正文内容")
    status: Optional[int] = Field(default=None, ge=0, le=2, description="状态：0=草稿 1=已发布 2=已下线")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")


class NewsData(DateTimeModel):
    """新闻数据"""
    uid: str = Field(..., description="新闻ID(字符串,避免前端精度丢失)")
    language: str = Field(..., description="语言: zh=中文 en=英文")
    title: str = Field(..., description="新闻标题")
    slug: str = Field(..., description="URL路径标识")
    summary: Optional[str] = Field(default=None, description="摘要")
    cover_image: Optional[str] = Field(default=None, description="封面图URL")
    content: Optional[str] = Field(default=None, description="Markdown正文内容")
    status: int = Field(..., description="状态：0=草稿 1=已发布 2=已下线")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class NewsListItem(DateTimeModel):
    """新闻列表项（不含content）"""
    uid: str = Field(..., description="新闻ID(字符串,避免前端精度丢失)")
    language: str = Field(..., description="语言: zh=中文 en=英文")
    title: str = Field(..., description="新闻标题")
    slug: str = Field(..., description="URL路径标识")
    summary: Optional[str] = Field(default=None, description="摘要")
    cover_image: Optional[str] = Field(default=None, description="封面图URL")
    status: int = Field(..., description="状态：0=草稿 1=已发布 2=已下线")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class NewsListResponseData(BaseModel):
    """新闻列表响应数据"""
    items: list[NewsListItem] = Field(..., description="新闻列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class NewsListResponse(AdminBaseResponse):
    """新闻列表响应"""
    data: Optional[NewsListResponseData] = None


class NewsResponse(AdminBaseResponse):
    """新闻响应"""
    data: Optional[NewsData] = None


