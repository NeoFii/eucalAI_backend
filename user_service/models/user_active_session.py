"""Current active session mapping."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from user_service.db import Base
from common.utils.timezone import now


class UserActiveSession(Base):
    """One active refresh session per user_service."""

    __tablename__ = "user_active_sessions"

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="User id",
    )
    session_id = Column(
        BigInteger,
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Current active session id",
    )
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False, comment="Updated at")

    user = relationship("User", back_populates="active_session", lazy="selectin")
    session = relationship("UserSession", back_populates="active_mapping", lazy="selectin")
