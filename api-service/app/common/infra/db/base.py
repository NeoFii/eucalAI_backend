"""Shared ORM mixins and declarative base for api-service."""

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy.orm import DeclarativeBase

from app.common.utils.timezone import now


class Base(DeclarativeBase):
    """Shared declarative base for all api-service ORM models."""

    pass


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


class SoftDeleteMixin:
    """Provide a nullable tombstone column for soft-delete semantics."""

    deleted_at = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Soft deleted at",
    )
