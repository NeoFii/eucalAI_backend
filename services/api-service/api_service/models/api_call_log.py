"""API call audit log model."""

from __future__ import annotations

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import relationship

from api_service.common.infra.db.base import Base, SnowflakeIdMixin
from api_service.common.utils.timezone import now


class ApiCallLog(Base, SnowflakeIdMixin):
    """Per-request audit log written by router-service."""

    __tablename__ = "api_call_logs"

    STATUS_SUCCESS = 200

    @staticmethod
    def is_success(status: int | None) -> bool:
        return status == 200

    @staticmethod
    def is_error(status: int | None) -> bool:
        return status is not None and status >= 400

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
    api_key = relationship("UserApiKey", lazy="raise", foreign_keys=[api_key_id])
    model_name = Column(String(64), nullable=False, comment="Requested model name")
    selected_model = Column(String(64), nullable=True, comment="Routed model name")
    provider_slug = Column(String(32), nullable=True, comment="Provider identifier")
    upstream_model = Column(String(64), nullable=True, comment="Upstream provider model name")
    config_version = Column(Integer, nullable=True, comment="Router config version")
    config_source = Column(String(32), nullable=True, comment="Config source (admin/local)")
    inference_config_version = Column(Integer, nullable=True, comment="Inference config version")
    inference_config_source = Column(String(32), nullable=True, comment="Inference config source")
    routing_tier = Column(SmallInteger, nullable=True, comment="Routing tier 1-5")
    score_source = Column(String(32), nullable=True, comment="Score source")
    total_score_0_10 = Column(
        DECIMAL(6, 4),
        nullable=True,
        comment="Routing total score 0-10 (DECIMAL(6,4))",
    )
    router_trace_id = Column(String(64), nullable=True, comment="Router trace ID")
    inference_error_code = Column(String(32), nullable=True, comment="Inference service error code")
    prompt_tokens = Column(Integer, default=0, nullable=False, comment="Prompt tokens")
    completion_tokens = Column(Integer, default=0, nullable=False, comment="Completion tokens")
    cached_tokens = Column(Integer, default=0, nullable=False, comment="Cache-hit tokens")
    total_tokens = Column(Integer, default=0, nullable=False, comment="prompt+completion+cached")
    cost = Column(BigInteger, default=0, nullable=False, comment="User-side total charge (微元)")
    provider_cost = Column(BigInteger, default=0, nullable=False, comment="Provider-side cost (微元)")
    cost_detail = Column(JSON, nullable=True, comment="Admin-only unit price breakdown")
    status = Column(
        SmallInteger,
        default=None,
        nullable=True,
        comment="HTTP status code: NULL=in-flight, 200=success, 4xx/5xx=error",
    )
    duration_ms = Column(Integer, nullable=True, comment="Request latency (ms)")
    upstream_latency_ms = Column(
        Integer,
        nullable=True,
        comment="Upstream LLM call latency (ms), separate from total duration",
    )
    is_stream = Column(Boolean, default=False, nullable=False, comment="0=non-stream 1=stream")
    messages_count = Column(
        SmallInteger,
        nullable=True,
        comment="Number of messages in the request",
    )
    ip = Column(String(45), nullable=True, comment="Caller IP; gated by user record_ip setting")
    error_code = Column(String(32), nullable=True, comment="Machine-readable error identifier")
    error_msg = Column(String(512), nullable=True, comment="Human-readable error message")
    routing_detail = Column(
        JSON,
        nullable=True,
        comment="Routing scoring detail (admin-visible): scores_0_2, proto_weighted, fallback_routes, tier_model_map, score_bands_raw",
    )
    request_preview = Column(
        JSON,
        nullable=True,
        comment="Request/response original text (super_admin only): {messages, response_text, is_truncated}",
    )
    input_hash = Column(
        String(32),
        nullable=True,
        comment="sha256(canonical(messages))[:32] for replay/compare view",
    )
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")
    updated_at = Column(
        DateTime,
        default=now,
        nullable=False,
        server_default=func.now(),
        comment="Updated at",
    )
