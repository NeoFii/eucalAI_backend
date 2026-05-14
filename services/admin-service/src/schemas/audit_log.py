"""Admin audit-log schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

from common.api import PaginatedResponse
from schemas.common import AdminBaseResponse, DateTimeModel

AdminAuditCategory = Literal[
    "all", "governance", "auth", "user_management", "model_catalog",
    "routing_config", "voucher", "pool",
]


class AdminAuditActor(BaseModel):
    """Admin summary embedded in audit-log responses."""

    uid: str = Field(..., description="Admin UID")
    email: str = Field(..., description="Admin email")
    name: str = Field(..., description="Admin name")
    role: str = Field(..., description="Admin role")

    @field_serializer("uid")
    def serialize_uid(self, value: str) -> str:
        return str(value)


class AdminAuditLogItem(DateTimeModel):
    """Admin audit-log list item."""

    id: int = Field(..., description="Audit log id")
    actor_admin: AdminAuditActor = Field(..., description="Actor admin")
    target_admin: Optional[AdminAuditActor] = Field(default=None, description="Target admin")
    action: str = Field(..., description="Audit action")
    action_label: str = Field(..., description="Action display name")
    resource_type: str = Field(..., description="Resource type")
    resource_id: Optional[str] = Field(default=None, description="Resource id")
    status: str = Field(..., description="success/failed")
    reason: Optional[str] = Field(default=None, description="Reason")
    ip_address: Optional[str] = Field(default=None, description="Source IP")
    user_agent: Optional[str] = Field(default=None, description="Source user agent")
    before_data: Optional[dict] = Field(default=None, description="Data before change")
    after_data: Optional[dict] = Field(default=None, description="Data after change")
    created_at: datetime = Field(..., description="Created at")


class AdminAuditLogListResponse(AdminBaseResponse):
    """Admin audit-log list response."""

    data: Optional[PaginatedResponse[AdminAuditLogItem]] = None


class AdminAuditLogMetaData(BaseModel):
    """Audit log filter metadata."""

    categories: list[str] = Field(..., description="Available category filters")
    action_labels: dict[str, str] = Field(..., description="Action to display name mapping")


class AdminAuditLogMetaResponse(AdminBaseResponse):
    """Audit log metadata response."""

    data: AdminAuditLogMetaData | None = None


class UpdateActionLabelRequest(BaseModel):
    """Request body for updating an action definition label."""

    label: str = Field(..., min_length=1, max_length=120, description="New display label")


class UpdateActionLabelResponse(AdminBaseResponse):
    """Response for action label update."""

    data: dict | None = None
