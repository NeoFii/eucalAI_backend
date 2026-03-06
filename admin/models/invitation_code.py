"""
邀请码数据模型
定义 invitation_codes 表结构
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, DateTime, SmallInteger, String, Text
from sqlalchemy.orm import relationship

from common.db.base import Base, SnowflakeIdMixin, TimestampMixin

if TYPE_CHECKING:
    from admin.models.admin_user import AdminUser


class InvitationCode(Base, SnowflakeIdMixin, TimestampMixin):
    """
    邀请码表
    存储用户注册邀请码信息
    """

    __tablename__ = "invitation_codes"

    # 邀请码（唯一）
    code = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="邀请码",
    )

    # 状态：0=未使用, 1=已使用, 2=已弃用
    status = Column(
        SmallInteger,
        default=0,
        nullable=False,
        comment="状态：0=未使用, 1=已使用, 2=已弃用",
    )

    # 创建者管理员 ID
    created_by = Column(
        BigInteger,
        nullable=True,
        comment="创建者管理员ID",
    )

    # 使用者用户 UID（被邀请注册的用户）
    used_by = Column(
        BigInteger,
        nullable=True,
        comment="使用者用户UID",
    )

    # 使用时间
    used_at = Column(
        DateTime,
        nullable=True,
        comment="使用时间",
    )

    # 过期时间
    expires_at = Column(
        DateTime,
        nullable=True,
        comment="过期时间",
    )

    # 备注
    remark = Column(
        Text,
        nullable=True,
        comment="备注",
    )

    def __repr__(self) -> str:
        return f"<InvitationCode(code={self.code}, status={self.status})>"

    @property
    def is_valid(self) -> bool:
        """检查邀请码是否有效"""
        if self.status != 0:
            return False
        if self.expires_at and self.expires_at < datetime.now():
            return False
        return True

    @property
    def is_used(self) -> bool:
        """检查邀请码是否已使用"""
        return self.status == 1

    @property
    def is_disabled(self) -> bool:
        """检查邀请码是否已弃用"""
        return self.status == 2

    @property
    def is_expired(self) -> bool:
        """检查邀请码是否已过期"""
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.now()
