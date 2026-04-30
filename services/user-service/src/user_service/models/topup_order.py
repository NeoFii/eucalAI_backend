"""Top-up order model."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin, TimestampMixin
from user_service.db import Base


class TopupOrder(Base, SnowflakeIdMixin, TimestampMixin):
    """One-shot top-up event."""

    __tablename__ = "topup_orders"

    STATUS_PENDING = 1
    STATUS_PAID = 2
    STATUS_CANCELLED = 3
    STATUS_REFUNDED = 4

    order_no = Column(String(64), unique=True, nullable=False, comment="Business order no, TP{yyyyMMdd}{8rand}")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK users.id",
    )
    amount = Column(BigInteger, nullable=False, comment="Top-up amount (微元)")
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="1=pending 2=paid 3=cancelled 4=refunded",
    )
    payment_channel = Column(
        String(32),
        default="manual",
        nullable=False,
        comment="manual / alipay / wechat / stripe",
    )
    payment_no = Column(String(128), nullable=True, comment="Third-party payment serial")
    payment_raw = Column(JSON, nullable=True, comment="Third-party callback raw payload")
    paid_at = Column(DateTime, nullable=True, comment="Paid timestamp")
    remark = Column(String(255), nullable=True, comment="Admin note")
    operator_id = Column(String(20), nullable=True, comment="Admin NanoID uid for manual top-ups")
