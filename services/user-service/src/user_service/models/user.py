"""User model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from user_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin
from common.utils.timezone import now


class User(Base, SnowflakeIdMixin, TimestampMixin):
    """User account."""

    __tablename__ = "users"

    uid = Column(String(20), unique=True, nullable=False, index=True, comment="Public user UID (NanoID)")
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment=(
            "Login email. Convention: store lowercase + trimmed at write time. "
            "MySQL default collation is case-insensitive so lookups work either way, "
            "but this convention keeps portability to PostgreSQL (case-sensitive by default) painless."
        ),
    )
    password_hash = Column(String(255), nullable=False, comment="Password hash")
    status = Column(SmallInteger, default=1, nullable=False, comment="0=disabled 1=active 2=pending")
    email_verified_at = Column(DateTime, nullable=True, comment="Email verified at")
    last_login_at = Column(DateTime, nullable=True, comment="Last login at")
    last_login_ip = Column(String(45), nullable=True, comment="Last login IP")
    login_fail_count = Column(Integer, default=0, nullable=False, comment="Failed login count")
    login_locked_until = Column(DateTime, nullable=True, comment="Login lock expiry")

    balance = Column(BigInteger, default=0, nullable=False, comment="可用余额（微元，¥1=1000000）")
    frozen_amount = Column(BigInteger, default=0, nullable=False, comment="预冻结中的余额（微元）")
    used_amount = Column(BigInteger, default=0, nullable=False, comment="历史累计消费（微元）")
    total_requests = Column(Integer, default=0, nullable=False, comment="历史累计调用次数")
    total_tokens = Column(BigInteger, default=0, nullable=False, comment="历史累计 token 数")

    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User(uid={self.uid}, email={self.email}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        return self.status == 1

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_login_locked(self) -> bool:
        if self.login_locked_until is None:
            return False
        return now() < self.login_locked_until
