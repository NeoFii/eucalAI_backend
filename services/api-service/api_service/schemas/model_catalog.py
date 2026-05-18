"""Public read-only model catalog schemas.

Ported from admin-service `src/schemas/model_catalog.py` (D-06: read subset
only). The 6 classes below mirror the source verbatim — only the import path
for `DateTimeModel` is rewritten to the api-service `schemas/common.py`.

Admin write payload schemas and the admin response envelope are intentionally
absent at Phase 4; Phase 5 will append them to this same file when the admin
domain ships (D-06 / D-10).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from api_service.schemas.common import DateTimeModel


class ModelVendorItem(DateTimeModel):
    id: int
    slug: str
    name: str
    logo_url: str | None = None
    is_active: bool
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelVendorBrief(BaseModel):
    id: int
    slug: str
    name: str
    logo_url: str | None = None


class ModelCategoryItem(DateTimeModel):
    id: int
    key: str
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelCategoryBrief(BaseModel):
    key: str
    name: str
    sort_order: int


class SupportedModelItem(DateTimeModel):
    id: int
    slug: str
    routing_slug: str | None = None
    name: str
    summary: str | None = None
    description: str | None = None
    sale_input_per_million: int | None = None
    sale_output_per_million: int | None = None
    sale_cached_input_per_million: int | None = None
    capability_tags: list[str] = Field(default_factory=list)
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_reasoning_model: bool
    is_active: bool
    sort_order: int
    vendor: ModelVendorBrief
    categories: list[ModelCategoryBrief] = Field(default_factory=list)


class SupportedModelDetail(SupportedModelItem):
    pass


__all__ = [
    "ModelCategoryBrief",
    "ModelCategoryItem",
    "ModelVendorBrief",
    "ModelVendorItem",
    "SupportedModelDetail",
    "SupportedModelItem",
]
