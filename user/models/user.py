"""
用户数据模型
定义 users 表结构
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, DateTime, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from common.db.base import Base, SnowflakeIdMixin, TimestampMixin
from common.utils.timezone import now

if TYPE_CHECKING:
    from user.models.user_session import UserSession


class User(Base, SnowflakeIdMixin, TimestampMixin):
    """
    用户主表
    存储用户基本信息和认证凭证

    注意：
    - id: 内部自增主键，用于表关联
    - uid: 对外使用的雪花 ID，接口中暴露此字段
    """

    __tablename__ = "users"

    # 对外用户 ID（雪花 ID）
    uid = Column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="对外用户ID（雪花ID）",
    )

    # 登录邮箱
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="登录邮箱",
    )

    # 密码哈希（bcrypt）
    password_hash = Column(
        String(255),
        nullable=False,
        comment="bcrypt密码哈希",
    )

    # 用户状态：0=禁用 1=正常 2=待验证
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="状态：0=禁用 1=正常 2=待验证",
    )

    # 邮箱验证时间
    email_verified_at = Column(
        DateTime,
        nullable=True,
        comment="邮箱验证时间",
    )

    # 最近登录时间
    last_login_at = Column(
        DateTime,
        nullable=True,
        comment="最近登录时间",
    )

    # 最近登录 IP
    last_login_ip = Column(
        String(45),
        nullable=True,
        comment="最近登录IP",
    )

    # 登录失败次数
    login_fail_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="登录失败次数",
    )

    # 登录锁定截止时间
    login_locked_until = Column(
        DateTime,
        nullable=True,
        comment="登录锁定截止时间",
    )

    # 关联关系：用户的会话列表
    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(uid={self.uid}, email={self.email}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        """检查用户是否处于正常状态"""
        return self.status == 1

    @property
    def is_email_verified(self) -> bool:
        """检查邮箱是否已验证"""
        return self.email_verified_at is not None

    @property
    def is_login_locked(self) -> bool:
        """检查登录是否被锁定"""
        if self.login_locked_until is None:
            return False
        return now() < self.login_locked_until
