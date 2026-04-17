"""Benchmarking schemas for testing-service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkJobAcceptedResponse(BaseModel):
    """Accepted benchmark job payload."""

    job_id: str
    job_type: str
    status: str
    accepted: bool
    queued_count: int


class BenchmarkJobStatusResponse(BaseModel):
    """Benchmark job status payload."""

    job_id: str
    job_type: str
    status: str
    trigger_source: Optional[str] = None
    requested_by_admin_id: Optional[int] = None
    scope_offering_id: Optional[int] = None
    total_offerings: int = 0
    completed_offerings: int = 0
    succeeded_offerings: int = 0
    failed_offerings: int = 0
    queued_count: int = 0
    error_message: Optional[str] = None
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminProbeAuditResponse(BaseModel):
    """Admin probe audit row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    offering_id: Optional[int] = None
    model_id: Optional[int] = None
    provider_id: Optional[int] = None
    triggered_by_admin_id: Optional[int] = None
    success: bool
    status: str
    error_code: Optional[str] = None
    ttft_ms: Optional[int] = None
    e2e_latency_ms: Optional[int] = None
    throughput_tps: Optional[float] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    probe_region: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AdminProbeAuditListResponse(BaseModel):
    """Probe audit list payload."""

    items: list[AdminProbeAuditResponse]
    total: int


class BenchmarkSummaryItem(BaseModel):
    """Benchmark summary row."""

    model_slug: str
    model_name: str
    vendor_name: str
    offerings: list[dict] = Field(default_factory=list)


class BenchmarkStatsSummaryResponse(BaseModel):
    """Benchmark summary payload."""

    items: list[BenchmarkSummaryItem]
    total: int


class TrendDataPoint(BaseModel):
    """Per-provider trend sample."""

    date: str
    avg_throughput_tps: Optional[float] = None
    avg_ttft_ms: Optional[int] = None
    avg_e2e_latency_ms: Optional[int] = None
    sample_count: int = 0


class ProviderTrendLine(BaseModel):
    """Trend line for one provider."""

    provider_id: int
    provider_name: str
    provider_slug: str
    provider_logo_url: Optional[str] = None
    data_points: list[TrendDataPoint] = Field(default_factory=list)
    min_throughput: Optional[float] = None
    max_throughput: Optional[float] = None
    avg_throughput: Optional[float] = None
    min_ttft: Optional[int] = None
    max_ttft: Optional[int] = None
    avg_ttft: Optional[int] = None


class BenchmarkTrendResponse(BaseModel):
    """Benchmark trend payload."""

    model_slug: str
    model_name: str
    days: int
    date_range: str
    providers: list[ProviderTrendLine] = Field(default_factory=list)
