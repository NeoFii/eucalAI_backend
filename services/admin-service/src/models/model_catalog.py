"""Admin-owned model catalog ORM models."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin


class ModelVendor(Base, SnowflakeIdMixin, TimestampMixin):
    """Company that builds a supported model."""

    __tablename__ = "model_vendors"

    slug = Column(String(80), unique=True, nullable=False, index=True, comment="Vendor slug")
    name = Column(String(120), nullable=False, comment="Vendor display name")
    logo_url = Column(String(512), nullable=True, comment="Vendor logo URL")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether vendor is active")
    sort_order = Column(Integer, nullable=False, default=0, comment="Display sort order")

    models = relationship(
        "SupportedModel",
        back_populates="vendor",
        lazy="noload",
    )


class ModelCategory(Base, SnowflakeIdMixin, TimestampMixin):
    """Capability category used to filter supported models."""

    __tablename__ = "model_categories"

    key = Column(String(80), unique=True, nullable=False, index=True, comment="Category key")
    name = Column(String(120), nullable=False, comment="Category display name")
    sort_order = Column(Integer, nullable=False, default=0, comment="Display sort order")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether category is active")

    model_links = relationship(
        "SupportedModelCategoryMap",
        back_populates="category",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class SupportedModel(Base, SnowflakeIdMixin, TimestampMixin):
    """Model exposed in the public catalog."""

    __tablename__ = "model_catalog"

    slug = Column(String(120), unique=True, nullable=False, index=True, comment="Model slug")
    routing_slug = Column(String(200), unique=True, nullable=True, index=True, comment="路由用 slug，对应 pool_model_configs.model_slug")
    name = Column(String(160), nullable=False, comment="Model display name")
    vendor_id = Column(
        BigInteger,
        ForeignKey("model_vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Model vendor id",
    )
    summary = Column(String(255), nullable=True, comment="Model card summary")
    description = Column(Text, nullable=True, comment="Model detail description")
    sale_input_per_million = Column(BigInteger, nullable=True, comment="用户售价（微元/百万token）")
    sale_output_per_million = Column(BigInteger, nullable=True, comment="用户售价（微元/百万token）")
    sale_cached_input_per_million = Column(BigInteger, nullable=True, comment="用户售价，缓存命中（微元/百万token）")
    capability_tags = Column(JSON, nullable=False, default=list, comment="Capability tag list")
    context_window = Column(Integer, nullable=True, comment="Context window tokens")
    max_output_tokens = Column(Integer, nullable=True, comment="Max output tokens")
    is_reasoning_model = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is a reasoning model",
    )
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether model is active")
    sort_order = Column(Integer, nullable=False, default=0, comment="Display sort order")

    vendor = relationship("ModelVendor", back_populates="models", lazy="selectin")
    category_links = relationship(
        "SupportedModelCategoryMap",
        back_populates="model",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="SupportedModelCategoryMap.sort_order",
    )


class SupportedModelCategoryMap(Base, SnowflakeIdMixin, TimestampMixin):
    """Many-to-many model/category mapping with model-local ordering."""

    __tablename__ = "model_catalog_category_map"
    __table_args__ = (
        UniqueConstraint("model_id", "category_id", name="uk_supported_model_category"),
    )

    model_id = Column(
        BigInteger,
        ForeignKey("model_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Supported model id",
    )
    category_id = Column(
        BigInteger,
        ForeignKey("model_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Model category id",
    )
    sort_order = Column(Integer, nullable=False, default=0, comment="Model-local category order")

    model = relationship("SupportedModel", back_populates="category_links", lazy="noload")
    category = relationship("ModelCategory", back_populates="model_links", lazy="noload")
