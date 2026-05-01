"""Hourly usage stats aggregate model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from common.db.base import SnowflakeIdMixin, TimestampMixin
from core.db import Base


class UsageStat(Base, SnowflakeIdMixin, TimestampMixin):
    """Hourly aggregate written by the user-service arq worker."""

    __tablename__ = "usage_stats"

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK users.id",
    )
    api_key_id = Column(
        BigInteger,
        ForeignKey("user_api_keys.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL = account-wide bucket",
    )
    account_api_key_id = Column(
        BigInteger,
        default=0,
        nullable=False,
        comment="api_key_id with NULL represented as 0 for uniqueness",
    )
    model_name = Column(String(64), nullable=False, comment="Logical model name")
    stat_hour = Column(DateTime, nullable=False, comment="Aligned to the hour (UTC)")
    request_count = Column(Integer, default=0, nullable=False, comment="Total calls")
    success_count = Column(Integer, default=0, nullable=False, comment="status=1 calls")
    error_count = Column(Integer, default=0, nullable=False, comment="status=2 calls")
    prompt_tokens = Column(BigInteger, default=0, nullable=False, comment="Prompt tokens sum")
    completion_tokens = Column(BigInteger, default=0, nullable=False, comment="Completion tokens sum")
    cached_tokens = Column(BigInteger, default=0, nullable=False, comment="Cache-hit tokens sum")
    total_tokens = Column(BigInteger, default=0, nullable=False, comment="Total tokens sum")
    total_cost = Column(BigInteger, default=0, nullable=False, comment="Total cost (微元)")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "api_key_id",
            "model_name",
            "stat_hour",
            name="uk_usage_stats_bucket",
        ),
        UniqueConstraint(
            "user_id",
            "account_api_key_id",
            "model_name",
            "stat_hour",
            name="uk_usage_stats_bucket_effective",
        ),
        Index("idx_usage_stats_user_hour", "user_id", "stat_hour"),
        Index("idx_usage_stats_key_hour", "api_key_id", "stat_hour"),
        Index("idx_usage_stats_hour", "stat_hour"),
    )
