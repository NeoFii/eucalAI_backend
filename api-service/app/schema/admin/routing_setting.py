"""Routing settings (admin) schemas.

Ported verbatim from `services/admin-service/src/schemas/routing_setting.py`
in Plan 05-02 / Task 2. The standard rewrites apply:

- `from schemas.common import AdminBaseResponse, DateTimeModel` →
  `from app.common.schemas import BaseResponse, DateTimeModel`
- `AdminBaseResponse` → `BaseResponse` (D-04 / Pitfall 8)

The source orders the batch-update classes such that
`RoutingSettingBatchUpdate` references `RoutingSettingBatchItem` BEFORE the
latter is declared. Pydantic v2 tolerates this when both are module-level
classes (it uses forward references), but for clarity Plan 05-02 reorders
the two classes — Item first, then BatchUpdate — and a `model_rebuild()`
call is unnecessary because no forward refs survive.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.common.schemas import BaseResponse, DateTimeModel


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


class RoutingSettingBatchItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1)


class RoutingSettingBatchUpdate(BaseModel):
    items: list[RoutingSettingBatchItem] = Field(..., min_length=1, max_length=20)


class RoutingSettingGroupResponse(BaseResponse):
    data: dict[str, list[RoutingSettingItem]] | None = None


class RoutingSettingResponse(BaseResponse):
    data: RoutingSettingItem | None = None


__all__ = [
    "RoutingSettingBatchItem",
    "RoutingSettingBatchUpdate",
    "RoutingSettingGroupResponse",
    "RoutingSettingItem",
    "RoutingSettingResponse",
    "RoutingSettingUpdate",
]
