"""Routing configuration and provider credential models."""

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from core.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin


class RoutingConfig(SnowflakeIdMixin, TimestampMixin, Base):
    """Versioned routing configuration snapshot."""

    __tablename__ = "routing_configs"

    version = Column(Integer, nullable=False, unique=True, comment="Monotonic version number")
    status = Column(
        String(16), nullable=False, default="draft", comment="draft / active / superseded"
    )
    config_data = Column(JSON, nullable=False, comment="Full routing policy JSON")
    description = Column(String(512), nullable=True, comment="Version description")
    published_at = Column(DateTime, nullable=True, comment="When this version was published")
    published_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who published this version",
    )
    created_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Admin who created this version",
    )

    publisher = relationship(
        "AdminUser", foreign_keys=[published_by], lazy="noload"
    )
    creator = relationship(
        "AdminUser", foreign_keys=[created_by], lazy="noload"
    )


class ProviderCredential(SnowflakeIdMixin, TimestampMixin, Base):
    """Encrypted upstream provider API credentials."""

    __tablename__ = "provider_credentials"

    slug = Column(String(64), nullable=False, unique=True, comment="Reference identifier")
    provider_slug = Column(String(64), nullable=False, comment="Provider identifier e.g. autodl")
    api_key_enc = Column(JSON, nullable=False, comment="AES-256-GCM encrypted {ciphertext,iv,tag}")
    mask = Column(String(32), nullable=False, comment="Masked display e.g. sk-1****89ab")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether credential is usable")
    remark = Column(String(256), nullable=True, comment="Optional note")
    created_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Admin who created this credential",
    )
    updated_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Admin who last updated this credential",
    )

    creator = relationship("AdminUser", foreign_keys=[created_by], lazy="noload")
    updater = relationship("AdminUser", foreign_keys=[updated_by], lazy="noload")
