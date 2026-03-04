"""
邀请码相关 Pydantic 模型
定义请求和响应的数据结构
"""

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.utils.timezone import format_iso, now, utc_to_shanghai


# ==================== 基础响应模型 ====================


class InvitationCodeBaseResponse(BaseModel):
    """邀请码基础响应"""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")


# ==================== 邀请码生成 ====================


class GenerateInvitationCodesRequest(BaseModel):
    """批量生成邀请码请求"""

    count: int = Field(..., ge=1, le=100, description="生成数量（1-100）")
    expires_at: datetime = Field(default_factory=lambda: now() + timedelta(days=7), description="过期时间（默认7天后）")
    remark: Optional[str] = Field(default=None, max_length=255, description="管理备注")

    @field_validator("expires_at")
    @classmethod
    def convert_to_shanghai_time(cls, v: datetime) -> datetime:
        """将传入的时间转换为上海时间（naive datetime）"""
        if v.tzinfo is not None:
            return utc_to_shanghai(v)
        return v


class InvitationCodeData(BaseModel):
    """邀请码数据"""

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda dt: format_iso(dt) if dt else None
        }
    )

    id: int = Field(..., description="邀请码ID")
    code: str = Field(..., description="邀请码字符串")
    status: int = Field(..., description="状态：0=未使用, 1=已使用, 2=已弃用")
    created_by: Optional[int] = Field(default=None, description="创建者uid")
    used_by: Optional[int] = Field(default=None, description="使用者uid")
    used_at: Optional[datetime] = Field(default=None, description="使用时间")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    remark: Optional[str] = Field(default=None, description="管理备注")
    created_at: datetime = Field(..., description="创建时间")


class GenerateInvitationCodesResponseData(BaseModel):
    """批量生成邀请码响应数据"""

    codes: list[InvitationCodeData] = Field(..., description="生成的邀请码列表")
    total: int = Field(..., description="生成数量")


class GenerateInvitationCodesResponse(InvitationCodeBaseResponse):
    """批量生成邀请码响应"""

    data: Optional[GenerateInvitationCodesResponseData] = None


# ==================== 邀请码列表查询 ====================


class GetInvitationCodeListRequest(BaseModel):
    """获取邀请码列表请求（Query参数）"""

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    status: Optional[int] = Field(default=None, ge=0, le=2, description="状态过滤：0=未使用, 1=已使用, 2=已弃用")


class GetInvitationCodeListResponseData(BaseModel):
    """获取邀请码列表响应数据"""

    items: list[InvitationCodeData] = Field(..., description="邀请码列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class GetInvitationCodeListResponse(InvitationCodeBaseResponse):
    """获取邀请码列表响应"""

    data: Optional[GetInvitationCodeListResponseData] = None


# ==================== 邀请码启用/弃用 ====================


class DisableInvitationCodeResponse(InvitationCodeBaseResponse):
    """弃用邀请码响应"""

    data: Optional[InvitationCodeData] = None


class EnableInvitationCodeResponse(InvitationCodeBaseResponse):
    """启用邀请码响应"""

    data: Optional[InvitationCodeData] = None
