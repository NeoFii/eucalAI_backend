"""Provider and offering schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProviderProbeConfigResponse(BaseModel):
    probe_api_base_url: Optional[str] = None
    has_probe_api_key: bool = False
    probe_api_key_masked: Optional[str] = None
    probe_key_updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProviderResponse(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool = True
    probe_config: Optional[ProviderProbeConfigResponse] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


class ProviderCreate(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool = True
    probe_api_base_url: Optional[str] = None
    probe_api_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None
    probe_api_base_url: Optional[str] = None
    probe_api_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ProviderBrief(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OfferingMetricsResponse(BaseModel):
    probe_region: Optional[str] = None
    avg_throughput_tps: Optional[float] = None
    avg_ttft_ms: Optional[int] = None
    avg_e2e_latency_ms: Optional[int] = None
    sample_count: int = 0
    last_measured_at: Optional[datetime] = None


class OfferingCreate(BaseModel):
    provider_id: int
    price_input_per_m: Optional[Decimal] = None
    price_output_per_m: Optional[Decimal] = None
    provider_model_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class PerformanceMetricCreate(BaseModel):
    offering_id: int
    throughput_tps: Optional[float] = None
    ttft_ms: Optional[int] = None
    e2e_latency_ms: Optional[int] = None
    success: bool = True
    error_code: Optional[str] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    probe_region: Optional[str] = None
    measured_at: datetime
