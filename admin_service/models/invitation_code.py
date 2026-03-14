"""Invitation code model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import relationship

from admin_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin
from common.utils.timezone import now

if TYPE_CHECKING:
    from admin_service.models.admin_user import AdminUser


class InvitationCode(Base, SnowflakeIdMixin, TimestampMixin):
    """Invitation code."""

    __tablename__ = "invitation_codes"

    code = Column(String(64), unique=True, nullable=False, index=True, comment="Invitation code")
    status = Column(SmallInteger, default=0, nullable=False, comment="0=unused 1=used 2=disabled")
    created_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Creator admin id",
    )
    # Keep UID semantics for now; registration flow still claims the code before the user row is committed.
    used_by = Column(BigInteger, nullable=True, index=True, comment="Used-by user UID")
    used_at = Column(DateTime, nullable=True, comment="Used at")
    expires_at = Column(DateTime, nullable=True, comment="Expires at")
    remark = Column(Text, nullable=True, comment="Remark")

    creator = relationship(
        "AdminUser",
        foreign_keys=[created_by],
        back_populates="created_invitation_codes",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<InvitationCode(code={self.code}, status={self.status})>"

    @property
    def is_valid(self) -> bool:
        if self.status != 0:
            return False
        if self.expires_at and self.expires_at < now():
            return False
        return True

    @property
    def is_used(self) -> bool:
        return self.status == 1

    @property
    def is_disabled(self) -> bool:
        return self.status == 2

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < now()
