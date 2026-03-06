"""
管理员数据模型
定义 admin_users 表结构
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, DateTime, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from common.db.base import Base, SnowflakeIdMixin, TimestampMixin

if TYPE_CHECKING:
    from admin.models.invitation_code import InvitationCode


class AdminUser(Base, SnowflakeIdMixin, TimestampMixin):
    """
    管理员用户表
    存储管理员基本信息和认证凭证
    """

    __tablename__ = "admin_users"

    # 对外管理员 ID（雪花 ID）
    uid = Column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="对外管理员ID（雪花ID）",
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

    # 管理员姓名
    name = Column(
        String(100),
        nullable=False,
        comment="管理员姓名",
    )

    # 管理员状态：0=禁用 1=正常
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="状态：0=禁用 1=正常",
    )

    # 角色：super=超级管理员 admin=普通管理员
    role = Column(
        String(20),
        default="admin",
        nullable=False,
        comment="角色：super=超级管理员 admin=普通管理员",
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

    def __repr__(self) -> str:
        return f"<AdminUser(uid={self.uid}, email={self.email}, role={self.role})>"

    @property
    def is_active(self) -> bool:
        """检查管理员是否处于正常状态"""
        return self.status == 1

    @property
    def is_super_admin(self) -> bool:
        """检查是否为超级管理员"""
        return self.role == "super"

    @property
    def is_login_locked(self) -> bool:
        """检查登录是否被锁定"""
        if self.login_locked_until is None:
            return False
        from common.utils.timezone import now
        return now() < self.login_locked_until
