"""Model catalog schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from testing_service.schemas.provider import OfferingMetricsResponse, ProviderBrief
from testing_service.schemas.vendor import ModelVendorBrief


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
