"""Admin audit-log schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

from admin_service.schemas.common import AdminBaseResponse, DateTimeModel

AdminAuditCategory = Literal["all", "governance", "auth"]


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
    resource_type: str = Field(..., description="Resource type")
    resource_id: Optional[str] = Field(default=None, description="Resource id")
    status: str = Field(..., description="success/failed")
    reason: Optional[str] = Field(default=None, description="Reason")
    ip_address: Optional[str] = Field(default=None, description="Source IP")
    user_agent: Optional[str] = Field(default=None, description="Source user agent")
    before_data: Optional[dict] = Field(default=None, description="Data before change")
    after_data: Optional[dict] = Field(default=None, description="Data after change")
    created_at: datetime = Field(..., description="Created at")


class AdminAuditLogListData(BaseModel):
    """Admin audit-log list response payload."""

    items: list[AdminAuditLogItem] = Field(..., description="Audit log list")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")


class AdminAuditLogListResponse(AdminBaseResponse):
    """Admin audit-log list response."""

    data: Optional[AdminAuditLogListData] = None
