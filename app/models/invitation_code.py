"""
邀请码数据模型
定义 invitation_codes 表结构，用于邀请注册机制
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Index
from sqlalchemy.orm import relationship

from app.db.base import Base, SnowflakeIdMixin, TimestampMixin
from app.utils.timezone import now

if TYPE_CHECKING:
    from app.models.user import User


class InvitationCode(Base, SnowflakeIdMixin, TimestampMixin):
    """
    邀请码表
    存储邀请码信息，用于控制用户注册

    状态说明：
    - 0 (unused): 未使用，可用于注册
    - 1 (used): 已使用，已被某用户注册消耗
    - 2 (disabled): 已弃用，管理员手动禁用

    注意：
    - code 字段对外暴露，使用高熵随机字符串（secrets.token_urlsafe(16) 生成）
    - id 是内部自增主键，用于表关联
    """

    __tablename__ = "invitation_codes"

    # 邀请码字符串（对外使用，唯一）
    code = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="邀请码字符串（22位高熵随机字符串）",
    )

    # 邀请码状态：0=未使用, 1=已使用, 2=已弃用
    status = Column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="状态：0=未使用, 1=已使用, 2=已弃用",
    )

    # 创建者 uid（预留，管理员创建时填写）
    created_by = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="创建者 uid（管理员）",
    )

    # 使用者 uid（注册成功后填写）
    used_by = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="使用者 uid（注册成功后填写）",
    )

    # 使用时间
    used_at = Column(
        DateTime,
        nullable=True,
        comment="使用时间",
    )

    # 过期时间（None 表示永不过期）
    expires_at = Column(
        DateTime,
        nullable=True,
        comment="过期时间（None表示永不过期）",
    )

    # 管理备注
    remark = Column(
        String(255),
        nullable=True,
        comment="管理备注",
    )

    def __repr__(self) -> str:
        return f"<InvitationCode(id={self.id}, code={self.code[:8]}..., status={self.status})>"

    @property
    def is_unused(self) -> bool:
        """检查邀请码是否未使用"""
        return self.status == 0

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
        return now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """检查邀请码是否有效（未使用且未过期且未弃用）"""
        return self.is_unused and not self.is_expired and not self.is_disabled
