# -*- coding: utf-8 -*-
"""Testing service Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None


class ListResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


class ModelVendorResponse(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ModelVendorBrief(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class VendorCreate(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None
    is_active: bool = True


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None


class ModelCategoryResponse(BaseModel):
    id: int
    key: str
    name: str
    sort_order: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ModelCategoryBrief(BaseModel):
    key: str
    name: str
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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


class ModelOfferingResponse(BaseModel):
    id: int
    provider: ProviderBrief
    price_input_per_m: Optional[Decimal] = None
    price_output_per_m: Optional[Decimal] = None
    provider_model_id: Optional[str] = None
    price_updated_at: Optional[datetime] = None
    is_active: bool
    metrics: Optional[OfferingMetricsResponse] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ModelListItem(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    capability_tags: List[str] = Field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    is_reasoning_model: bool = False
    sort_order: int = 0
    vendor: Optional[ModelVendorBrief] = None
    categories: List[ModelCategoryBrief] = Field(default_factory=list)
    provider_count: int = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


class ModelDetailResponse(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    capability_tags: List[str] = Field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    is_reasoning_model: bool = False
    is_active: bool = True
    vendor: Optional[ModelVendorBrief] = None
    categories: List[ModelCategoryBrief] = Field(default_factory=list)
    offerings: List[ModelOfferingResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


class ModelCategoryAssign(BaseModel):
    category_id: int
    sort_order: int = 0


class ModelCreate(BaseModel):
    vendor_id: Optional[int] = None
    slug: str
    name: str
    description: Optional[str] = None
    capability_tags: List[str] = Field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    is_reasoning_model: bool = False
    sort_order: int = 0
    is_active: bool = True
    categories: List[ModelCategoryAssign] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    capability_tags: Optional[List[str]] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    is_reasoning_model: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    categories: Optional[List[ModelCategoryAssign]] = None

    model_config = ConfigDict(extra="forbid")


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
