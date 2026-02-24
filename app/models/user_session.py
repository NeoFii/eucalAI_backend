"""
用户会话模型
定义 user_sessions 表结构
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, ForeignKey, String, Text, DateTime
from sqlalchemy.orm import relationship

from app.db.base import Base, SnowflakeIdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserSession(Base, SnowflakeIdMixin, TimestampMixin):
    """
    用户会话表
    管理用户登录会话和 refresh_token

    注意：
    - 互踢模式：一个用户只允许一个活跃会话
    - 新登录会自动使旧会话失效（通过 revoked_at 标记）
    """

    __tablename__ = "user_sessions"

    # 对外会话 ID（雪花 ID）
    session_id = Column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="对外会话ID（雪花ID）",
    )

    # 关联用户（内部自增 ID）
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户ID",
    )

    # refresh_token 哈希
    refresh_token_hash = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="refresh_token哈希",
    )

    # 客户端标识
    user_agent = Column(
        String(512),
        nullable=True,
        comment="客户端User-Agent",
    )

    # 登录 IP
    ip_address = Column(
        String(45),
        nullable=True,
        comment="登录IP地址",
    )

    # 过期时间
    expires_at = Column(
        DateTime,
        nullable=False,
        comment="会话过期时间",
    )

    # 主动注销时间（用于软删除）
    revoked_at = Column(
        DateTime,
        nullable=True,
        comment="主动注销时间",
    )

    # 关联关系：所属用户
    user = relationship(
        "User",
        back_populates="sessions",
    )

    def __repr__(self) -> str:
        return f"<UserSession(session_id={self.session_id}, user_id={self.user_id}, revoked={self.is_revoked})>"

    @property
    def is_revoked(self) -> bool:
        """检查会话是否已注销"""
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        """检查会话是否已过期"""
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    @property
    def is_valid(self) -> bool:
        """检查会话是否有效（未注销且未过期）"""
        return not self.is_revoked and not self.is_expired
