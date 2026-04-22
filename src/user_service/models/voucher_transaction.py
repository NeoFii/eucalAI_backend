"""Voucher transaction model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin
from common.utils.timezone import now
from user_service.db import Base


class VoucherTransaction(Base, SnowflakeIdMixin):
    """Append-only ledger for voucher mutations."""

    __tablename__ = "voucher_transactions"

    TYPE_ISSUE = 1
    TYPE_FREEZE = 2
    TYPE_CONSUME = 3
    TYPE_RELEASE = 4
    TYPE_ADMIN_UPDATE = 5
    TYPE_DELETE = 6

    voucher_id = Column(
        BigInteger,
        ForeignKey("user_vouchers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK user_vouchers.id",
    )
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK users.id",
    )
    type = Column(
        SmallInteger,
        nullable=False,
        comment="1=ISSUE 2=FREEZE 3=CONSUME 4=RELEASE 5=ADMIN_UPDATE 6=DELETE",
    )
    amount = Column(Integer, nullable=False, comment="Voucher amount delta (fen)")
    balance_before = Column(Integer, nullable=False, comment="Remaining amount before change (fen)")
    balance_after = Column(Integer, nullable=False, comment="Remaining amount after change (fen)")
    ref_type = Column(String(32), nullable=True, comment="api_call / admin")
    ref_id = Column(String(64), nullable=True, comment="Related document id")
    operator_id = Column(BigInteger, nullable=True, comment="Admin uid when applicable")
    remark = Column(String(255), nullable=True, comment="Admin/system note")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")
