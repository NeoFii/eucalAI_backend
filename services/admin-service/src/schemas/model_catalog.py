"""Model catalog API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse


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
    price_input_per_m_fen: int | None = None
    price_output_per_m_fen: int | None = None
    price_cached_input_per_m_fen: int | None = None
    capability_tags: list[str] = Field(default_factory=list)
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_reasoning_model: bool
    sort_order: int
    vendor: ModelVendorBrief
    categories: list[ModelCategoryBrief] = Field(default_factory=list)


class SupportedModelDetail(SupportedModelItem):
    is_active: bool


class ModelVendorCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=80, pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
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
    key: str = Field(..., min_length=1, max_length=80, pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
    name: str = Field(..., min_length=1, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True


class ModelCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None


class SupportedModelCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
    routing_slug: str | None = Field(default=None, max_length=200)
    name: str = Field(..., min_length=1, max_length=160)
    vendor_slug: str = Field(..., min_length=1, max_length=80, pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
    summary: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    price_input_per_m_fen: int | None = Field(default=None, ge=0)
    price_output_per_m_fen: int | None = Field(default=None, ge=0)
    price_cached_input_per_m_fen: int | None = Field(default=None, ge=0)
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
        import re

        _slug_re = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
        seen: set[str] = set()
        for key in v:
            if len(key) > 80:
                raise ValueError("each category key must be <= 80 characters")
            if not _slug_re.match(key):
                raise ValueError(f"invalid category key format: {key!r}")
            if key in seen:
                raise ValueError(f"duplicate category key: {key}")
            seen.add(key)
        return v


class SupportedModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    routing_slug: str | None = Field(default=None, max_length=200)
    vendor_slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
    summary: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    price_input_per_m_fen: int | None = Field(default=None, ge=0)
    price_output_per_m_fen: int | None = Field(default=None, ge=0)
    price_cached_input_per_m_fen: int | None = Field(default=None, ge=0)
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
            import re

            _slug_re = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
            if len(v) > 20:
                raise ValueError("category_keys must have at most 20 items")
            seen: set[str] = set()
            for key in v:
                if len(key) > 80:
                    raise ValueError("each category key must be <= 80 characters")
                if not _slug_re.match(key):
                    raise ValueError(f"invalid category key format: {key!r}")
                if key in seen:
                    raise ValueError(f"duplicate category key: {key}")
                seen.add(key)
        return v


class ModelVendorListResponse(AdminBaseResponse):
    data: PaginatedResponse[ModelVendorItem] | None = None


class ModelVendorResponse(AdminBaseResponse):
    data: ModelVendorItem | None = None


class ModelCategoryListResponse(AdminBaseResponse):
    data: PaginatedResponse[ModelCategoryItem] | None = None


class ModelCategoryResponse(AdminBaseResponse):
    data: ModelCategoryItem | None = None


class SupportedModelListResponse(AdminBaseResponse):
    data: PaginatedResponse[SupportedModelItem] | None = None


class SupportedModelResponse(AdminBaseResponse):
    data: SupportedModelDetail | None = None


class ModelCatalogOperationResponse(AdminBaseResponse):
    pass
