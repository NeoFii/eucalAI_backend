"""Balance transaction ledger model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin
from common.utils.timezone import now
from user_service.db import Base


class BalanceTransaction(Base, SnowflakeIdMixin):
    """Immutable append-only ledger for every balance mutation."""

    __tablename__ = "balance_transactions"

    TYPE_TOPUP = 1
    TYPE_CONSUME = 2
    TYPE_REFUND = 3
    TYPE_FREEZE = 4
    TYPE_UNFREEZE = 5
    TYPE_ADMIN_ADJUST = 6
    TYPE_VOUCHER_REDEEM = 7

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK users.id",
    )
    type = Column(
        SmallInteger,
        nullable=False,
        comment="1=TOPUP 2=CONSUME 3=REFUND 4=FREEZE 5=UNFREEZE 6=ADMIN_ADJUST 7=VOUCHER_REDEEM",
    )
    amount = Column(Integer, nullable=False, comment="Positive=increase, negative=decrease (分)")
    balance_before = Column(Integer, nullable=False, comment="balance snapshot before change (分)")
    balance_after = Column(Integer, nullable=False, comment="balance snapshot after change (分)")
    ref_type = Column(String(32), nullable=True, comment="topup_order / api_call / voucher_code")
    ref_id = Column(String(64), nullable=True, comment="related document id")
    remark = Column(String(255), nullable=True, comment="admin/system note")
    operator_id = Column(String(20), nullable=True, comment="admin NanoID uid when type=ADMIN_ADJUST")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")
