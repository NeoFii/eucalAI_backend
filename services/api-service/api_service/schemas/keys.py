"""API key schema split for api-service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api_service.common.utils.timezone import to_shanghai_naive
from api_service.schemas.common import DateTimeModel
from api_service.common.utils.api_key_policy import normalize_allow_ips, normalize_allowed_models


class ApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    quota_mode: int = Field(default=1, ge=1, le=2)
    quota_limit: int = Field(default=0, ge=0)
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("allowed_models")
    @classmethod
    def normalize_allowed_models_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allowed_models(value)

    @field_validator("allow_ips")
    @classmethod
    def normalize_allow_ips_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allow_ips(value)

    @field_validator("expires_at", mode="after")
    @classmethod
    def normalize_expires_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        return to_shanghai_naive(value)


class ApiKeyCreateData(BaseModel):
    key: str
    item: ApiKeyItem


class ApiKeyUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    quota_limit: Optional[int] = Field(default=None, gt=0)
    reset_quota_used: bool = False
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("allowed_models")
    @classmethod
    def normalize_allowed_models_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allowed_models(value)

    @field_validator("allow_ips")
    @classmethod
    def normalize_allow_ips_field(cls, value: Optional[str]) -> Optional[str]:
        return normalize_allow_ips(value)

    @field_validator("expires_at", mode="after")
    @classmethod
    def normalize_expires_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        return to_shanghai_naive(value)


__all__ = [
    "ApiKeyCreateData",
    "ApiKeyCreateRequest",
    "ApiKeyItem",
    "ApiKeyUpdateRequest",
]
