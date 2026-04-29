"""Voucher redemption code model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from common.db.base import SnowflakeIdMixin, TimestampMixin
from user_service.db import Base


class VoucherRedemptionCode(Base, SnowflakeIdMixin, TimestampMixin):
    """Hash-only voucher code that can be redeemed into normal user balance."""

    __tablename__ = "voucher_redemption_codes"

    STATUS_ACTIVE = 1
    STATUS_REDEEMED = 2
    STATUS_DISABLED = 3

    code_hash = Column(String(64), unique=True, nullable=False, comment="SHA-256 hash of normalized code")
    code_prefix = Column(String(8), nullable=False, comment="Non-secret display prefix")
    code_suffix = Column(String(8), nullable=False, comment="Non-secret display suffix")
    amount = Column(Integer, nullable=False, comment="Redeem amount (fen)")
    status = Column(
        SmallInteger,
        default=STATUS_ACTIVE,
        nullable=False,
        comment="1=active 2=redeemed 3=disabled",
    )
    starts_at = Column(DateTime, nullable=False, index=True, comment="Code validity start")
    expires_at = Column(DateTime, nullable=False, index=True, comment="Code validity end")
    redeemed_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Redeeming users.id",
    )
    redeemed_at = Column(DateTime, nullable=True, comment="Redeemed at")
    created_by_admin_uid = Column(String(20), nullable=True, index=True, comment="Creator admin uid (NanoID)")
    remark = Column(String(255), nullable=True, comment="Admin note")

    redeemed_user = relationship("User", lazy="selectin")

    @property
    def redeemed_user_uid(self) -> str | None:
        if self.redeemed_user is None:
            return None
        return self.redeemed_user.uid
