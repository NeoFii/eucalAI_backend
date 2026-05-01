"""Routing settings schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.common import AdminBaseResponse, DateTimeModel


class RoutingSettingItem(DateTimeModel):
    key: str
    value: str
    value_type: str
    group_name: str
    label: str
    description: str | None
    sort_order: int
    updated_at: datetime


class RoutingSettingUpdate(BaseModel):
    value: str = Field(..., min_length=1)


class RoutingSettingBatchUpdate(BaseModel):
    items: list[RoutingSettingBatchItem] = Field(..., min_length=1, max_length=20)


class RoutingSettingBatchItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1)


class RoutingSettingGroupResponse(AdminBaseResponse):
    data: dict[str, list[RoutingSettingItem]] | None = None


class RoutingSettingResponse(AdminBaseResponse):
    data: RoutingSettingItem | None = None
