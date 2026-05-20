"""User API key model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String

from app.common.infra.db.base import Base, SnowflakeIdMixin, SoftDeleteMixin, TimestampMixin


class UserApiKey(Base, SnowflakeIdMixin, TimestampMixin, SoftDeleteMixin):
    """User-owned API key — pure service credential."""

    __tablename__ = "user_api_keys"

    STATUS_ACTIVE = 1
    STATUS_DISABLED = 2

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
        comment="1=active 2=disabled",
    )
    last_used_at = Column(DateTime, nullable=True, comment="Last successful validation")
