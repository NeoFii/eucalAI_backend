"""Router billing models."""

from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, ForeignKey, Integer, String, Text

from router_service.db import Base
from common.utils.timezone import now


class RouterUsageEvent(Base):
    """Per-request usage record."""

    __tablename__ = "router_usage_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    request_id = Column(String(64), nullable=False, unique=True, index=True, comment="Idempotency request id")
    router_api_key_id = Column(
        BigInteger,
        ForeignKey("router_api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Router API key id",
    )
    owner_user_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Owner user id",
    )
    key_hash = Column(String(64), nullable=False, index=True, comment="Router key hash")
    endpoint = Column(String(64), nullable=False, comment="Endpoint path")
    provider_slug = Column(String(100), nullable=True, index=True, comment="Resolved provider slug")
    requested_model = Column(String(255), nullable=False, comment="Requested model")
    resolved_model = Column(String(255), nullable=False, comment="Resolved logical model")
    usage_source = Column(String(20), nullable=False, default="none", comment="actual/estimated/none")
    prompt_tokens = Column(Integer, nullable=False, default=0, comment="Prompt tokens")
    completion_tokens = Column(Integer, nullable=False, default=0, comment="Completion tokens")
    total_tokens = Column(Integer, nullable=False, default=0, comment="Total tokens")
    input_price_per_m = Column(DECIMAL(18, 6), nullable=True, comment="Input price snapshot per million tokens")
    output_price_per_m = Column(DECIMAL(18, 6), nullable=True, comment="Output price snapshot per million tokens")
    cost_input = Column(DECIMAL(18, 6), nullable=False, default=0, comment="Input cost")
    cost_output = Column(DECIMAL(18, 6), nullable=False, default=0, comment="Output cost")
    cost_total = Column(DECIMAL(18, 6), nullable=False, default=0, comment="Total cost")
    currency = Column(String(16), nullable=False, default="CNY", comment="Billing currency")
    status_code = Column(Integer, nullable=False, comment="HTTP status code")
    error_code = Column(String(128), nullable=True, comment="Error code")
    error_message = Column(Text, nullable=True, comment="Error detail")
    latency_ms = Column(Integer, nullable=True, comment="Latency milliseconds")
    created_at = Column(DateTime, nullable=False, default=now, index=True, comment="Created at")


class RouterBillingLedger(Base):
    """Immutable ledger rows for router billing."""

    __tablename__ = "router_billing_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    usage_event_id = Column(
        BigInteger,
        ForeignKey("router_usage_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Source usage event id",
    )
    router_api_key_id = Column(
        BigInteger,
        ForeignKey("router_api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Router API key id",
    )
    owner_user_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Owner user id",
    )
    direction = Column(String(16), nullable=False, comment="debit/credit/adjust")
    amount = Column(DECIMAL(18, 6), nullable=False, comment="Ledger amount")
    currency = Column(String(16), nullable=False, default="CNY", comment="Currency")
    balance_before = Column(DECIMAL(18, 6), nullable=True, comment="Balance before change")
    balance_after = Column(DECIMAL(18, 6), nullable=True, comment="Balance after change")
    description = Column(String(255), nullable=True, comment="Description")
    created_at = Column(DateTime, nullable=False, default=now, index=True, comment="Created at")
