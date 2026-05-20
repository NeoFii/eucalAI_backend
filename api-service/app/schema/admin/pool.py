"""Pool management schemas (admin domain).

Ported from `services/admin-service/src/schemas/pool.py` in Plan 05-02 /
Task 1. Rewrites applied:

- `from schemas.common import AdminBaseResponse, DateTimeModel` →
  `from app.common.schemas import BaseResponse, DateTimeModel`
- `from common.api import PaginatedResponse` →
  `from app.common.api.pagination import PaginatedResponse`
- `class XxxResponse(AdminBaseResponse)` → `class XxxResponse(BaseResponse)`
  (D-04 / Pitfall 8)
- `from core.enums import PoolAccountStatus` →
  `from app.model.enums import PoolAccountStatus` (Phase 2 layout —
  same fix Plan 05-01 applied)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.common.api.pagination import PaginatedResponse
from app.common.schemas import BaseResponse, DateTimeModel


# ---------------------------------------------------------------------------
# PoolModel (号池支持的模型)
# ---------------------------------------------------------------------------

class PoolModelCreate(BaseModel):
    model_slug: str = Field(..., min_length=1, max_length=120)
    upstream_model_id: str = Field(..., min_length=1, max_length=200)
    cost_input_per_million: int = Field(default=0, ge=0)
    cost_output_per_million: int = Field(default=0, ge=0)
    cost_cached_input_per_million: int | None = Field(default=None, ge=0)
    context_length: int | None = Field(default=None, ge=1)


class PoolModelUpdate(BaseModel):
    upstream_model_id: str | None = Field(default=None, min_length=1, max_length=200)
    cost_input_per_million: int | None = Field(default=None, ge=0)
    cost_output_per_million: int | None = Field(default=None, ge=0)
    cost_cached_input_per_million: int | None = Field(default=None, ge=0)
    context_length: int | None = Field(default=None, ge=1)
    is_enabled: bool | None = None


class PoolModelItem(BaseModel):
    id: int
    model_slug: str
    upstream_model_id: str
    cost_input_per_million: int
    cost_output_per_million: int
    cost_cached_input_per_million: int | None
    context_length: int | None
    is_enabled: bool


# ---------------------------------------------------------------------------
# PoolAccount (号池账号)
# ---------------------------------------------------------------------------

class PoolAccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    api_key: str = Field(..., min_length=1, description="Plaintext API key (encrypted at rest)")
    balance: int = Field(default=0, ge=0)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    weight: int = Field(default=1, ge=1)
    remark: str | None = Field(default=None, max_length=256)


class PoolAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    api_key: str | None = Field(default=None, min_length=1)
    balance: int | None = Field(default=None, ge=0)
    status: int | None = Field(default=None, ge=0, le=3)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    weight: int | None = Field(default=None, ge=1)
    remark: str | None = Field(default=None, max_length=256)


class PoolAccountItem(DateTimeModel):
    id: int
    name: str
    mask: str
    balance: int
    status: int
    rpm_limit: int | None
    tpm_limit: int | None
    weight: int
    last_checked_at: datetime | None
    remark: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Pool (号池)
# ---------------------------------------------------------------------------

class PoolCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field(..., min_length=1, max_length=512)
    priority: int = Field(default=0, ge=0)
    weight: int = Field(default=1, ge=1)
    health_check_endpoint: str | None = Field(default=None, max_length=512)
    remark: str | None = Field(default=None, max_length=256)


class PoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=1)
    health_check_endpoint: str | None = Field(default=None, max_length=512)
    remark: str | None = Field(default=None, max_length=256)


class PoolItem(DateTimeModel):
    id: int
    slug: str
    name: str
    base_url: str
    is_enabled: bool
    priority: int
    weight: int
    health_check_endpoint: str | None
    remark: str | None
    model_count: int
    account_count: int
    created_at: datetime
    updated_at: datetime


class PoolDetail(DateTimeModel):
    id: int
    slug: str
    name: str
    base_url: str
    is_enabled: bool
    priority: int
    weight: int
    health_check_endpoint: str | None
    remark: str | None
    models: list[PoolModelItem]
    accounts: list[PoolAccountItem]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------

class PoolResponse(BaseResponse):
    data: PoolItem | None = None


class PoolDetailResponse(BaseResponse):
    data: PoolDetail | None = None


class PoolListResponse(BaseResponse):
    data: PaginatedResponse[PoolItem] | None = None


class PoolModelResponse(BaseResponse):
    data: PoolModelItem | None = None


class PoolAccountResponse(BaseResponse):
    data: PoolAccountItem | None = None


# ---------------------------------------------------------------------------
# Automation results
# ---------------------------------------------------------------------------

class SyncModelsResult(BaseModel):
    added: list[str]
    updated: list[str]
    existing: list[str]
    total_upstream: int


class AccountBalanceResult(BaseModel):
    account_id: int
    name: str
    balance: int
    status: int
    error: str | None = None


class CheckBalancesResult(BaseModel):
    results: list[AccountBalanceResult]


class SyncModelsResponse(BaseResponse):
    data: SyncModelsResult | None = None


class CheckBalancesResponse(BaseResponse):
    data: CheckBalancesResult | None = None


# ---------------------------------------------------------------------------
# Available model slugs (for tier model selection)
# ---------------------------------------------------------------------------

class AvailableModelSlugItem(BaseModel):
    model_slug: str
    pool_names: list[str]


class AvailableModelSlugsResponse(BaseResponse):
    data: list[AvailableModelSlugItem] | None = None


# ---------------------------------------------------------------------------
# Model cost info (for profit margin display)
# ---------------------------------------------------------------------------

class ModelCostPoolItem(BaseModel):
    pool_name: str
    cost_input_per_million: int
    cost_output_per_million: int
    cost_cached_input_per_million: int | None


class ModelCostInfo(BaseModel):
    model_slug: str
    min_cost_input_per_million: int
    min_cost_output_per_million: int
    min_cost_cached_input_per_million: int | None
    pools: list[ModelCostPoolItem]


class ModelCostResponse(BaseResponse):
    data: ModelCostInfo | None = None


__all__ = [
    "AccountBalanceResult",
    "AvailableModelSlugItem",
    "AvailableModelSlugsResponse",
    "CheckBalancesResponse",
    "CheckBalancesResult",
    "ModelCostInfo",
    "ModelCostPoolItem",
    "ModelCostResponse",
    "PoolAccountCreate",
    "PoolAccountItem",
    "PoolAccountResponse",
    "PoolAccountUpdate",
    "PoolCreate",
    "PoolDetail",
    "PoolDetailResponse",
    "PoolItem",
    "PoolListResponse",
    "PoolModelCreate",
    "PoolModelItem",
    "PoolModelResponse",
    "PoolModelUpdate",
    "PoolResponse",
    "PoolUpdate",
    "SyncModelsResponse",
    "SyncModelsResult",
]
