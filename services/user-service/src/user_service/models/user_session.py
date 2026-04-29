"""User session model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from user_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin
from common.utils.timezone import now


class UserSession(Base, SnowflakeIdMixin, TimestampMixin):
    """Refresh-token session."""

    __tablename__ = "user_sessions"

    session_id = Column(BigInteger, unique=True, nullable=False, index=True, comment="Public session id")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user id",
    )
    token_jti = Column(String(64), unique=True, nullable=False, index=True, comment="Refresh token jti hash")
    refresh_token_hash = Column(String(255), nullable=False, comment="Refresh token hash")
    user_agent = Column(String(512), nullable=True, comment="User agent")
    ip_address = Column(String(45), nullable=True, comment="IP address")
    expires_at = Column(DateTime, nullable=False, comment="Expires at")
    revoked_at = Column(DateTime, nullable=True, comment="Revoked at")

    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession(session_id={self.session_id}, user_id={self.user_id}, revoked={self.is_revoked})>"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired
