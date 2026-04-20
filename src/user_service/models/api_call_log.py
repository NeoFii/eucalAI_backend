"""API call audit log model."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, SmallInteger, String

from common.db.base import SnowflakeIdMixin
from common.utils.timezone import now
from user_service.db import Base


class ApiCallLog(Base, SnowflakeIdMixin):
    """Per-request audit log written by router-service."""

    __tablename__ = "api_call_logs"

    STATUS_SUCCESS = 1
    STATUS_ERROR = 2
    STATUS_REFUNDED = 3

    request_id = Column(
        String(64),
        unique=True,
        nullable=False,
        comment="Global request id, spans 3-phase billing",
    )
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
        comment="FK user_api_keys.id, NULL if key not used",
    )
    model_name = Column(String(64), nullable=False, comment="Logical model name")
    prompt_tokens = Column(Integer, default=0, nullable=False, comment="Prompt tokens")
    completion_tokens = Column(Integer, default=0, nullable=False, comment="Completion tokens")
    cached_tokens = Column(Integer, default=0, nullable=False, comment="Cache-hit tokens")
    total_tokens = Column(Integer, default=0, nullable=False, comment="prompt+completion+cached")
    cost = Column(Integer, default=0, nullable=False, comment="User-side total charge (分)")
    cost_detail = Column(JSON, nullable=True, comment="Admin-only unit price breakdown")
    status = Column(
        SmallInteger,
        default=1,
        nullable=False,
        comment="1=success 2=error 3=refunded",
    )
    duration_ms = Column(Integer, nullable=True, comment="Request latency (ms)")
    is_stream = Column(Boolean, default=False, nullable=False, comment="0=non-stream 1=stream")
    ip = Column(String(45), nullable=True, comment="Caller IP; gated by user record_ip setting")
    error_code = Column(String(32), nullable=True, comment="status=2 payload")
    error_msg = Column(String(512), nullable=True, comment="status=2 message")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")
