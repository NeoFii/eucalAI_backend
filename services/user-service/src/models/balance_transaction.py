"""Balance transaction ledger model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin
from common.utils.timezone import now
from core.db import Base


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
    amount = Column(BigInteger, nullable=False, comment="Positive=increase, negative=decrease (微元)")
    balance_before = Column(BigInteger, nullable=False, comment="balance snapshot before change (微元)")
    balance_after = Column(BigInteger, nullable=False, comment="balance snapshot after change (微元)")
    ref_type = Column(String(32), nullable=True, comment="topup_order / api_call / voucher_code")
    ref_id = Column(String(64), nullable=True, comment="related document id")
    remark = Column(String(255), nullable=True, comment="admin/system note")
    operator_id = Column(String(20), nullable=True, comment="admin NanoID uid when type=ADMIN_ADJUST")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.ref_type is None or self.ref_id is None:
            raise ValueError(
                f"BalanceTransaction requires ref_type and ref_id for idempotency "
                f"(type={self.type}, ref_type={self.ref_type}, ref_id={self.ref_id})"
            )
