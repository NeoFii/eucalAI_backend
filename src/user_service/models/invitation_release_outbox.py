"""Invitation-release outbox model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Index, Integer, String

from common.db.base import SnowflakeIdMixin, TimestampMixin
from user_service.db import Base


class InvitationReleaseOutbox(Base, SnowflakeIdMixin, TimestampMixin):
    """Compensation queue for failed invitation-code releases."""

    __tablename__ = "invitation_release_outbox"

    code = Column(String(64), nullable=False, comment="Invitation code to release")
    used_by_uid = Column(
        BigInteger,
        nullable=False,
        comment="Snowflake uid of the failed registrant",
    )
    retry_count = Column(Integer, default=0, nullable=False, comment="Worker retry counter")
    last_error = Column(String(255), nullable=True, comment="Last worker error message")

    __table_args__ = (
        Index("idx_invitation_release_outbox_retry", "retry_count", "updated_at"),
    )
