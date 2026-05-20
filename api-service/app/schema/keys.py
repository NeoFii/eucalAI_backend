"""API key schema for api-service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.common.schemas import DateTimeModel


class ApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str
    name: str
    status: int
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyCreateData(BaseModel):
    key: str
    item: ApiKeyItem


class ApiKeyUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


__all__ = [
    "ApiKeyCreateData",
    "ApiKeyCreateRequest",
    "ApiKeyItem",
    "ApiKeyUpdateRequest",
]
