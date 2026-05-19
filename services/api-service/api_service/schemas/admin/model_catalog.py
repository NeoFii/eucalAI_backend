"""Admin-side write schemas for the model catalog.

Phase 4 04-03 already ported the READ-side schemas to
`api_service/schemas/model_catalog.py` (ModelVendorItem, ModelCategoryItem,
SupportedModelItem, SupportedModelDetail, brief models). Plan 05-02 ports
the WRITE-side payload schemas + admin response wrappers verbatim from
`services/admin-service/src/schemas/model_catalog.py` with the standard
rewrites:

- `from schemas.common import AdminBaseResponse, DateTimeModel` →
  `from api_service.common.schemas import BaseResponse, DateTimeModel`
- `from common.api import PaginatedResponse` →
  `from api_service.common.api.pagination import PaginatedResponse`
- `AdminBaseResponse` → `BaseResponse` (D-04 / Pitfall 8)

The READ-side schemas are re-imported from
`api_service.schemas.model_catalog` so the admin schema module stays the
single source of truth for the response wrappers.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from api_service.common.api.pagination import PaginatedResponse
from api_service.common.schemas import BaseResponse
from api_service.schemas.model_catalog import (
    ModelCategoryBrief,
    ModelCategoryItem,
    ModelVendorBrief,
    ModelVendorItem,
    SupportedModelDetail,
    SupportedModelItem,
)


# ---------------------------------------------------------------------------
# Write payloads (admin only)
# ---------------------------------------------------------------------------

class ModelVendorCreate(BaseModel):
    slug: str = Field(
        ...,
        min_length=1, max_length=80,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$",
    )
    name: str = Field(..., min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=512)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=9999)


class ModelVendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class ModelCategoryCreate(BaseModel):
    key: str = Field(
        ...,
        min_length=1, max_length=80,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$",
    )
    name: str = Field(..., min_length=1, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True


class ModelCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None


_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")


class SupportedModelCreate(BaseModel):
    slug: str = Field(
        ...,
        min_length=1, max_length=120,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$",
    )
    routing_slug: str | None = Field(default=None, max_length=200)
    name: str = Field(..., min_length=1, max_length=160)
    vendor_slug: str = Field(
        ...,
        min_length=1, max_length=80,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$",
    )
    summary: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    sale_input_per_million: int | None = Field(default=None, ge=0)
    sale_output_per_million: int | None = Field(default=None, ge=0)
    sale_cached_input_per_million: int | None = Field(default=None, ge=0)
    capability_tags: list[str] = Field(default_factory=list, max_length=20)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    is_reasoning_model: bool = False
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=9999)
    category_keys: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("capability_tags")
    @classmethod
    def validate_capability_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if len(tag) > 50:
                raise ValueError("each capability tag must be <= 50 characters")
        return v

    @field_validator("category_keys")
    @classmethod
    def validate_category_keys(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        for key in v:
            if len(key) > 80:
                raise ValueError("each category key must be <= 80 characters")
            if not _SLUG_RE.match(key):
                raise ValueError(f"invalid category key format: {key!r}")
            if key in seen:
                raise ValueError(f"duplicate category key: {key}")
            seen.add(key)
        return v


class SupportedModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    routing_slug: str | None = Field(default=None, max_length=200)
    vendor_slug: str | None = Field(
        default=None,
        min_length=1, max_length=80,
        pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$",
    )
    summary: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    sale_input_per_million: int | None = Field(default=None, ge=0)
    sale_output_per_million: int | None = Field(default=None, ge=0)
    sale_cached_input_per_million: int | None = Field(default=None, ge=0)
    capability_tags: list[str] | None = None
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    is_reasoning_model: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    category_keys: list[str] | None = None

    @field_validator("capability_tags")
    @classmethod
    def validate_capability_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 20:
                raise ValueError("capability_tags must have at most 20 items")
            for tag in v:
                if len(tag) > 50:
                    raise ValueError("each capability tag must be <= 50 characters")
        return v

    @field_validator("category_keys")
    @classmethod
    def validate_category_keys(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 20:
                raise ValueError("category_keys must have at most 20 items")
            seen: set[str] = set()
            for key in v:
                if len(key) > 80:
                    raise ValueError("each category key must be <= 80 characters")
                if not _SLUG_RE.match(key):
                    raise ValueError(f"invalid category key format: {key!r}")
                if key in seen:
                    raise ValueError(f"duplicate category key: {key}")
                seen.add(key)
        return v


# ---------------------------------------------------------------------------
# Response wrappers (admin)
# ---------------------------------------------------------------------------

class ModelVendorListResponse(BaseResponse):
    data: PaginatedResponse[ModelVendorItem] | None = None


class ModelVendorResponse(BaseResponse):
    data: ModelVendorItem | None = None


class ModelCategoryListResponse(BaseResponse):
    data: PaginatedResponse[ModelCategoryItem] | None = None


class ModelCategoryResponse(BaseResponse):
    data: ModelCategoryItem | None = None


class SupportedModelListResponse(BaseResponse):
    data: PaginatedResponse[SupportedModelItem] | None = None


class SupportedModelResponse(BaseResponse):
    data: SupportedModelDetail | None = None


class ModelCatalogOperationResponse(BaseResponse):
    pass


__all__ = [
    "ModelCatalogOperationResponse",
    "ModelCategoryBrief",
    "ModelCategoryCreate",
    "ModelCategoryItem",
    "ModelCategoryListResponse",
    "ModelCategoryResponse",
    "ModelCategoryUpdate",
    "ModelVendorBrief",
    "ModelVendorCreate",
    "ModelVendorItem",
    "ModelVendorListResponse",
    "ModelVendorResponse",
    "ModelVendorUpdate",
    "SupportedModelCreate",
    "SupportedModelDetail",
    "SupportedModelItem",
    "SupportedModelListResponse",
    "SupportedModelResponse",
    "SupportedModelUpdate",
]
