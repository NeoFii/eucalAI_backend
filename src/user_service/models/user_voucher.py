"""User voucher model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin, SoftDeleteMixin, TimestampMixin
from common.utils.timezone import now
from user_service.db import Base


class UserVoucher(Base, SnowflakeIdMixin, TimestampMixin, SoftDeleteMixin):
    """User-owned prepaid credit voucher."""

    __tablename__ = "user_vouchers"

    STATUS_ACTIVE = 1
    STATUS_DISABLED = 2

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK users.id",
    )
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="1=active 2=disabled",
    )
    original_amount = Column(Integer, nullable=False, comment="Initial voucher amount (fen)")
    remaining_amount = Column(Integer, default=0, nullable=False, comment="Unfrozen usable amount (fen)")
    frozen_amount = Column(Integer, default=0, nullable=False, comment="Frozen amount (fen)")
    used_amount = Column(Integer, default=0, nullable=False, comment="Consumed amount (fen)")
    expires_at = Column(DateTime, nullable=True, index=True, comment="NULL = never expires")
    created_by_admin_uid = Column(BigInteger, nullable=True, index=True, comment="Creator admin uid")
    remark = Column(String(255), nullable=True, comment="Admin note")

    @property
    def is_available(self) -> bool:
        if self.deleted_at is not None:
            return False
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.remaining_amount <= 0:
            return False
        return not (self.expires_at is not None and self.expires_at <= now())
