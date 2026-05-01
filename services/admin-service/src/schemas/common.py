"""Shared admin-service response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_serializer

from common.utils.timezone import format_iso


class AdminBaseResponse(BaseModel):
    """Admin base response."""

    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")


class DateTimeModel(BaseModel):
    """Serialize datetime fields through the project timezone formatter."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AdminErrorResponse(AdminBaseResponse):
    """Admin error response."""

    code: int = Field(default=400, description="错误码")
    message: str = Field(default="error", description="错误消息")
