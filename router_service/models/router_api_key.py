"""Router API key model."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, DECIMAL, Integer, String, Text

from router_service.db import Base
from common.db.base import TimestampMixin


class RouterAPIKey(Base, TimestampMixin):
    """User-owned API key used to access the router service."""

    __tablename__ = "router_api_keys"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    owner_user_id = Column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Owner user id",
    )
    name = Column(String(100), nullable=False, comment="User-defined key name")
    key_hash = Column(String(64), nullable=False, unique=True, index=True, comment="SHA-256 key hash")
    key_ciphertext = Column(Text, nullable=True, comment="Encrypted raw key payload")
    token_preview = Column(String(32), nullable=False, comment="Masked key preview")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether the key is active")
    is_deleted = Column(Boolean, nullable=False, default=False, index=True, comment="Whether the key is deleted")
    last_used_at = Column(DateTime, nullable=True, comment="Last used timestamp")
    billing_mode = Column(String(20), nullable=False, default="postpaid", comment="prepaid/postpaid")
    balance = Column(DECIMAL(18, 6), nullable=True, comment="Prepaid balance")
    daily_quota_tokens = Column(BigInteger, nullable=True, comment="Daily token quota")
    monthly_quota_tokens = Column(BigInteger, nullable=True, comment="Monthly token quota")
    daily_quota_cost = Column(DECIMAL(18, 6), nullable=True, comment="Daily cost quota")
    monthly_quota_cost = Column(DECIMAL(18, 6), nullable=True, comment="Monthly cost quota")
    rate_limit_rpm = Column(Integer, nullable=True, comment="Per-key request limit per minute")
