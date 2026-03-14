# -*- coding: utf-8 -*-
"""Testing service SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DECIMAL,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from testing_service.db import Base
from common.db.base import TimestampMixin
from common.utils.timezone import now


class ModelCategory(Base, TimestampMixin):
    __tablename__ = "model_categories"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    key = Column(String(50), nullable=False, unique=True, comment="Category key")
    name = Column(String(100), nullable=False, comment="Display name")
    sort_order = Column(SmallInteger, nullable=False, default=0, comment="Sort order")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether active")

    category_maps = relationship(
        "ModelCategoryMap",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ModelVendor(Base, TimestampMixin):
    __tablename__ = "model_vendors"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    slug = Column(String(100), nullable=False, unique=True, comment="Vendor slug")
    name = Column(String(200), nullable=False, comment="Display name")
    logo_url = Column(Text, comment="Logo URL")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether active")
    deleted_at = Column(DateTime, nullable=True, comment="Soft delete time")

    models = relationship("Model", back_populates="vendor", lazy="selectin")

    __table_args__ = (
        Index("idx_model_vendors_is_active", "is_active"),
        Index("idx_model_vendors_deleted_at", "deleted_at"),
    )


class Model(Base, TimestampMixin):
    __tablename__ = "models"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    vendor_id = Column(BigInteger, ForeignKey("model_vendors.id"), nullable=False, comment="Vendor id")
    slug = Column(String(100), nullable=False, unique=True, comment="Model slug")
    name = Column(String(200), nullable=False, comment="Display name")
    description = Column(Text, comment="Description")
    capability_tags = Column(JSON, nullable=False, comment="Capability tags")
    context_window = Column(Integer, comment="Context window")
    max_output_tokens = Column(Integer, comment="Max output tokens")
    is_reasoning_model = Column(Boolean, nullable=False, default=False, comment="Reasoning model flag")
    sort_order = Column(Integer, nullable=False, default=0, comment="Sort order")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether active")

    vendor = relationship("ModelVendor", back_populates="models", lazy="selectin")
    category_maps = relationship(
        "ModelCategoryMap",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    offerings = relationship(
        "ModelProviderOffering",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_models_vendor_id", "vendor_id"),
        Index("idx_models_is_active", "is_active"),
        Index("idx_models_sort_order", "sort_order"),
    )


class ModelCategoryMap(Base):
    __tablename__ = "model_category_map"

    model_id = Column(
        BigInteger,
        ForeignKey("models.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Model id",
    )
    category_id = Column(
        BigInteger,
        ForeignKey("model_categories.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Category id",
    )
    sort_order = Column(Integer, nullable=False, default=0, comment="Sort order in category")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")

    model = relationship("Model", back_populates="category_maps")
    category = relationship("ModelCategory", back_populates="category_maps")

    __table_args__ = (Index("idx_mcm_category_sort", "category_id", "sort_order"),)


class ProviderProbeConfig(Base, TimestampMixin):
    __tablename__ = "provider_probe_configs"

    provider_id = Column(
        BigInteger,
        ForeignKey("providers.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Provider id",
    )
    probe_api_base_url = Column(Text, nullable=True, comment="Probe API base URL")
    probe_api_key_ciphertext = Column(Text, nullable=True, comment="Encrypted API key")
    probe_api_key_iv = Column(Text, nullable=True, comment="API key IV")
    probe_api_key_tag = Column(Text, nullable=True, comment="API key tag")
    probe_api_key_masked = Column(String(50), nullable=True, comment="Masked API key")
    probe_key_updated_at = Column(DateTime, nullable=True, comment="Probe key updated at")
    key_updated_by_admin_id = Column(BigInteger, nullable=True, comment="Key updater admin id")

    provider = relationship("Provider", back_populates="probe_config", lazy="selectin")

    @property
    def has_probe_api_key(self) -> bool:
        return bool(
            self.probe_api_key_ciphertext
            and self.probe_api_key_iv
            and self.probe_api_key_tag
        )


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    slug = Column(String(100), nullable=False, unique=True, comment="Provider slug")
    name = Column(String(200), nullable=False, comment="Display name")
    logo_url = Column(Text, comment="Logo URL")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether active")
    deleted_at = Column(DateTime, nullable=True, comment="Soft delete time")

    probe_config = relationship(
        "ProviderProbeConfig",
        back_populates="provider",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    offerings = relationship(
        "ModelProviderOffering",
        back_populates="provider",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_providers_is_active", "is_active"),
        Index("idx_providers_deleted_at", "deleted_at"),
    )

    def _ensure_probe_config(self) -> ProviderProbeConfig:
        if self.probe_config is None:
            self.probe_config = ProviderProbeConfig()
        return self.probe_config

    @property
    def probe_api_base_url(self):
        return self.probe_config.probe_api_base_url if self.probe_config else None

    @probe_api_base_url.setter
    def probe_api_base_url(self, value):
        self._ensure_probe_config().probe_api_base_url = value

    @property
    def probe_api_key_ciphertext(self):
        return self.probe_config.probe_api_key_ciphertext if self.probe_config else None

    @probe_api_key_ciphertext.setter
    def probe_api_key_ciphertext(self, value):
        self._ensure_probe_config().probe_api_key_ciphertext = value

    @property
    def probe_api_key_iv(self):
        return self.probe_config.probe_api_key_iv if self.probe_config else None

    @probe_api_key_iv.setter
    def probe_api_key_iv(self, value):
        self._ensure_probe_config().probe_api_key_iv = value

    @property
    def probe_api_key_tag(self):
        return self.probe_config.probe_api_key_tag if self.probe_config else None

    @probe_api_key_tag.setter
    def probe_api_key_tag(self, value):
        self._ensure_probe_config().probe_api_key_tag = value

    @property
    def probe_api_key_masked(self):
        return self.probe_config.probe_api_key_masked if self.probe_config else None

    @probe_api_key_masked.setter
    def probe_api_key_masked(self, value):
        self._ensure_probe_config().probe_api_key_masked = value

    @property
    def probe_key_updated_at(self):
        return self.probe_config.probe_key_updated_at if self.probe_config else None

    @probe_key_updated_at.setter
    def probe_key_updated_at(self, value):
        self._ensure_probe_config().probe_key_updated_at = value


class ModelProviderOffering(Base, TimestampMixin):
    __tablename__ = "model_provider_offerings"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    model_id = Column(
        BigInteger,
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        comment="Model id",
    )
    provider_id = Column(
        BigInteger,
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Provider id",
    )
    price_input_per_m = Column(DECIMAL(10, 4), comment="Input price per million tokens")
    price_output_per_m = Column(DECIMAL(10, 4), comment="Output price per million tokens")
    api_base_url = Column(Text, comment="Legacy per-offering API base URL")
    price_updated_at = Column(DateTime, comment="Price updated at")
    price_updated_by = Column(String(100), comment="Legacy price updater label")
    price_updated_by_admin_id = Column(BigInteger, nullable=True, comment="Price updater admin id")
    provider_model_name = Column(String(200), comment="Provider-side model name")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether active")
    deleted_at = Column(DateTime, nullable=True, comment="Soft delete time")
    created_by_admin_id = Column(BigInteger, nullable=True, comment="Creator admin id")
    updated_by_admin_id = Column(BigInteger, nullable=True, comment="Updater admin id")

    model = relationship("Model", back_populates="offerings")
    provider = relationship("Provider", back_populates="offerings", lazy="selectin")
    performance_metrics = relationship(
        "ProviderPerformanceMetric",
        back_populates="offering",
        cascade="all, delete-orphan",
    )
    daily_stats = relationship(
        "ProviderPerformanceDailyStat",
        back_populates="offering",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("model_id", "provider_id", name="uk_mpo_model_provider"),
        Index("idx_mpo_model_id", "model_id"),
        Index("idx_mpo_provider_id", "provider_id"),
        Index("idx_mpo_is_active", "is_active"),
        Index("idx_mpo_deleted_at", "deleted_at"),
    )


class ProviderPerformanceMetric(Base):
    __tablename__ = "provider_performance_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    offering_id = Column(
        BigInteger,
        ForeignKey("model_provider_offerings.id", ondelete="CASCADE"),
        nullable=False,
        comment="Offering id",
    )
    throughput_tps = Column(DECIMAL(8, 2), comment="Throughput in tokens/s")
    ttft_ms = Column(Integer, comment="Time to first token in ms")
    e2e_latency_ms = Column(Integer, comment="End-to-end latency in ms")
    success = Column(Boolean, nullable=False, default=True, comment="Whether success")
    error_code = Column(String(50), comment="Failure code")
    prompt_tokens = Column(Integer, comment="Prompt tokens")
    output_tokens = Column(Integer, comment="Output tokens")
    probe_region = Column(String(50), comment="Probe region")
    measured_at = Column(DateTime, nullable=False, comment="Measured at")

    offering = relationship("ModelProviderOffering", back_populates="performance_metrics")

    __table_args__ = (
        Index("idx_ppm_offering_time", "offering_id", "measured_at"),
        Index("idx_ppm_offering_region", "offering_id", "probe_region"),
        Index("idx_ppm_success_time", "success", "measured_at"),
    )


class ProviderPerformanceDailyStat(Base, TimestampMixin):
    __tablename__ = "provider_performance_daily_stats"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    offering_id = Column(
        BigInteger,
        ForeignKey("model_provider_offerings.id", ondelete="CASCADE"),
        nullable=False,
        comment="Offering id",
    )
    probe_region = Column(String(50), nullable=False, comment="Probe region")
    stat_date = Column(Date, nullable=False, comment="Stat date")
    sample_count = Column(Integer, nullable=False, default=0, comment="Sample count")
    success_count = Column(Integer, nullable=False, default=0, comment="Success count")
    fail_count = Column(Integer, nullable=False, default=0, comment="Fail count")
    avg_throughput_tps = Column(DECIMAL(10, 2), nullable=True, comment="Average throughput")
    avg_ttft_ms = Column(Integer, nullable=True, comment="Average TTFT")
    avg_e2e_latency_ms = Column(Integer, nullable=True, comment="Average E2E latency")
    min_throughput_tps = Column(DECIMAL(10, 2), nullable=True, comment="Min throughput")
    max_throughput_tps = Column(DECIMAL(10, 2), nullable=True, comment="Max throughput")
    min_ttft_ms = Column(Integer, nullable=True, comment="Min TTFT")
    max_ttft_ms = Column(Integer, nullable=True, comment="Max TTFT")
    last_measured_at = Column(DateTime, nullable=True, comment="Last measured at")

    offering = relationship("ModelProviderOffering", back_populates="daily_stats", lazy="selectin")

    __table_args__ = (
        UniqueConstraint(
            "offering_id",
            "probe_region",
            "stat_date",
            name="uk_provider_performance_daily_stats",
        ),
        Index("idx_ppds_date", "stat_date"),
        Index("idx_ppds_offering_date", "offering_id", "stat_date"),
    )


class BenchmarkJob(Base, TimestampMixin):
    __tablename__ = "benchmark_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    job_id = Column(String(64), nullable=False, unique=True, comment="Public benchmark job id")
    job_type = Column(String(16), nullable=False, comment="full/single")
    status = Column(String(20), nullable=False, default="queued", comment="queued/running/succeeded/failed/partial")
    requested_by_admin_id = Column(
        BigInteger,
        nullable=True,
        comment="Triggering admin id",
    )
    scope_offering_id = Column(
        BigInteger,
        ForeignKey("model_provider_offerings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Target offering id for single probe",
    )
    trigger_source = Column(String(20), nullable=False, default="manual", comment="manual/scheduler")
    total_offerings = Column(Integer, nullable=False, default=0, comment="Total offerings in this job")
    completed_offerings = Column(Integer, nullable=False, default=0, comment="Completed offerings count")
    succeeded_offerings = Column(Integer, nullable=False, default=0, comment="Succeeded offerings count")
    failed_offerings = Column(Integer, nullable=False, default=0, comment="Failed offerings count")
    queued_at = Column(DateTime, nullable=True, comment="Queued at")
    started_at = Column(DateTime, nullable=True, comment="Started at")
    finished_at = Column(DateTime, nullable=True, comment="Finished at")
    error_message = Column(Text, nullable=True, comment="Last job error message")

    offering = relationship("ModelProviderOffering", lazy="selectin")

    __table_args__ = (
        Index("idx_benchmark_jobs_status", "status"),
        Index("idx_benchmark_jobs_job_type", "job_type"),
        Index("idx_benchmark_jobs_requested_by", "requested_by_admin_id"),
        Index("idx_benchmark_jobs_scope_offering", "scope_offering_id"),
        Index("idx_benchmark_jobs_created_at", "created_at"),
    )


class AdminProbeAuditLog(Base, TimestampMixin):
    __tablename__ = "admin_probe_audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    job_id = Column(String(64), nullable=False, comment="Benchmark job id")
    offering_id = Column(
        BigInteger,
        ForeignKey("model_provider_offerings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Offering id",
    )
    model_id = Column(
        BigInteger,
        ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True,
        comment="Model id",
    )
    provider_id = Column(
        BigInteger,
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
        comment="Provider id",
    )
    triggered_by_admin_id = Column(
        BigInteger,
        nullable=True,
        comment="Triggering admin id",
    )
    status = Column(String(20), nullable=False, comment="completed/failed")
    success = Column(Boolean, nullable=False, default=False, comment="Whether the manual probe succeeded")
    error_code = Column(String(128), nullable=True, comment="Failure code")
    ttft_ms = Column(Integer, nullable=True, comment="Time to first token in ms")
    e2e_latency_ms = Column(Integer, nullable=True, comment="End-to-end latency in ms")
    throughput_tps = Column(DECIMAL(10, 2), nullable=True, comment="Throughput in tokens/s")
    prompt_tokens = Column(Integer, nullable=True, comment="Prompt token count")
    output_tokens = Column(Integer, nullable=True, comment="Output token count")
    probe_region = Column(String(50), nullable=True, comment="Probe region")
    started_at = Column(DateTime, nullable=True, comment="Started at")
    finished_at = Column(DateTime, nullable=True, comment="Finished at")

    offering = relationship("ModelProviderOffering", lazy="selectin")
    model = relationship("Model", lazy="selectin")
    provider = relationship("Provider", lazy="selectin")

    __table_args__ = (
        Index("idx_admin_probe_audits_job_id", "job_id"),
        Index("idx_admin_probe_audits_offering_id", "offering_id"),
        Index("idx_admin_probe_audits_admin_id", "triggered_by_admin_id"),
        Index("idx_admin_probe_audits_created_at", "created_at"),
    )


class ProviderMetricsRanked(Base):
    __tablename__ = "provider_metrics_ranked"

    offering_id = Column(BigInteger, primary_key=True, comment="Offering id")
    probe_region = Column(String(50), primary_key=True, comment="Probe region")
    measured_at = Column(DateTime, primary_key=True, comment="Measured at")
    throughput_tps = Column(DECIMAL(8, 2), comment="Throughput in tokens/s")
    ttft_ms = Column(Integer, comment="TTFT in ms")
    e2e_latency_ms = Column(Integer, comment="E2E latency in ms")
    rn = Column(Integer, comment="Ranking number")

    __table_args__ = ({"info": {"is_view": True}},)
