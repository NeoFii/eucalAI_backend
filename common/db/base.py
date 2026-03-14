"""Shared ORM mixins reused by service-local declarative bases."""

from sqlalchemy import BigInteger, Column, DateTime

from common.utils.timezone import now


class TimestampMixin:
    """Provide shared created/updated timestamp columns."""

    created_at = Column(
        DateTime,
        default=now,
        nullable=False,
        comment="Created at",
    )
    updated_at = Column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
        comment="Updated at",
    )


class SnowflakeIdMixin:
    """Provide a shared internal bigint primary-key column."""

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="Internal primary key",
    )