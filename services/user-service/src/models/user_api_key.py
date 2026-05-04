"""User API key model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, Text

from common.db.base import SnowflakeIdMixin, SoftDeleteMixin, TimestampMixin
from core.db import Base


class UserApiKey(Base, SnowflakeIdMixin, TimestampMixin, SoftDeleteMixin):
    """User-owned API key used by router-service."""

    __tablename__ = "user_api_keys"

    STATUS_ACTIVE = 1
    STATUS_DISABLED = 2
    STATUS_EXPIRED = 3
    STATUS_EXHAUSTED = 4

    MODE_UNLIMITED = 1
    MODE_LIMITED = 2

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK users.id",
    )
    key_hash = Column(String(128), unique=True, nullable=False, comment="SHA-256 of raw key")
    key_prefix = Column(String(12), nullable=False, comment="First 8 plaintext chars for UI")
    name = Column(String(100), nullable=False, comment="User-defined name")
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="1=active 2=disabled 3=expired 4=exhausted",
    )
    quota_mode = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="1=unlimited 2=limited",
    )
    quota_limit = Column(BigInteger, default=0, nullable=False, comment="limited-mode cap (微元)")
    quota_used = Column(BigInteger, default=0, nullable=False, comment="Cumulative spend via this key (微元)")
    allowed_models = Column(Text, nullable=True, comment="comma-separated model names, NULL=all")
    allow_ips = Column(Text, nullable=True, comment="newline-separated CIDRs, NULL=all")
    expires_at = Column(DateTime, nullable=True, comment="NULL = never expires")
    last_used_at = Column(DateTime, nullable=True, comment="Last successful validation")

    @property
    def is_exhausted(self) -> bool:
        return self.quota_mode == self.MODE_LIMITED and self.quota_used >= self.quota_limit
