"""Routing configuration and provider credential schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse

FIVEWAY_ROUTE_ORDER = ("纠错", "工具调用", "通用任务", "任务拆解", "编程")


# ── Provider Credential schemas ──────────────────────────────────────


class CredentialCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    provider_slug: str = Field(..., min_length=1, max_length=64)
    api_key: str = Field(..., min_length=1, description="Plaintext API key (encrypted at rest)")
    remark: str | None = Field(default=None, max_length=256)


class CredentialUpdate(BaseModel):
    provider_slug: str | None = Field(default=None, min_length=1, max_length=64)
    api_key: str | None = Field(default=None, min_length=1)
    remark: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None


class CredentialItem(DateTimeModel):
    id: int
    slug: str
    provider_slug: str
    mask: str
    is_active: bool
    remark: str | None
    created_at: datetime
    updated_at: datetime


class CredentialListResponse(AdminBaseResponse):
    data: PaginatedResponse[CredentialItem] | None = None


class CredentialResponse(AdminBaseResponse):
    data: CredentialItem | None = None


# ── Routing Config schemas ───────────────────────────────────────────


class ModelProviderBinding(BaseModel):
    credential_slug: str = Field(..., min_length=1, max_length=64)
    api_base: str = Field(..., min_length=1)
    upstream_model: str = Field(..., min_length=1)


class RoutingConfigData(BaseModel):
    router_alias: str = Field(default="auto", min_length=1)
    weights: dict[str, float]
    score_bands: str = Field(..., min_length=1)
    tier_model_map: dict[str, str]
    model_provider_bindings: dict[str, ModelProviderBinding]

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: dict[str, float]) -> dict[str, float]:
        expected = set(FIVEWAY_ROUTE_ORDER)
        if set(v.keys()) != expected:
            raise ValueError(f"weights must contain exactly: {list(FIVEWAY_ROUTE_ORDER)}")
        if any(val < 0 for val in v.values()):
            raise ValueError("weights must be non-negative")
        if sum(v.values()) <= 0:
            raise ValueError("weights sum must be greater than 0")
        return v

    @field_validator("tier_model_map")
    @classmethod
    def validate_tier_model_map(cls, v: dict[str, str]) -> dict[str, str]:
        expected = {"1", "2", "3", "4", "5"}
        if set(v.keys()) != expected:
            raise ValueError("tier_model_map must define tiers 1..5")
        for tier, model in v.items():
            if not model.strip():
                raise ValueError(f"tier_model_map[{tier}] must not be empty")
        return v


class RoutingConfigCreate(BaseModel):
    description: str | None = Field(default=None, max_length=512)
    config_data: RoutingConfigData


class RoutingConfigUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=512)
    config_data: RoutingConfigData | None = None


class RoutingConfigItem(DateTimeModel):
    id: int
    version: int
    status: str
    description: str | None
    config_data: dict
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoutingConfigBrief(DateTimeModel):
    id: int
    version: int
    status: str
    description: str | None
    published_at: datetime | None
    created_at: datetime


class RoutingConfigResponse(AdminBaseResponse):
    data: RoutingConfigItem | None = None


class RoutingConfigListResponse(AdminBaseResponse):
    data: PaginatedResponse[RoutingConfigBrief] | None = None


# ── Internal endpoint response schemas ───────────────────────────────


class InternalRoutingConfigFull(BaseModel):
    """Response for /internal/routing-config/active/full (router-service)."""

    version: int
    status: str
    router_alias: str
    route_order: list[str]
    weights: dict[str, float]
    score_bands: str
    tier_model_map: dict[str, str]
    model_providers: dict[str, dict[str, str]]


class InternalRoutingConfigInference(BaseModel):
    """Response for /internal/routing-config/active/inference (inference-service)."""

    version: int
    status: str
    route_order: list[str]
    weights: dict[str, float]
    score_bands: str
    tier_model_map: dict[str, str]
