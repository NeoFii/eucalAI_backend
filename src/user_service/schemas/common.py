"""Shared schema primitives for user-service packages."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field, model_serializer

from common.utils.timezone import format_iso

T = TypeVar("T")


class DateTimeModel(BaseModel):
    """Serialize datetimes as ISO strings."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AuthBaseResponse(BaseModel):
    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")


class AuthErrorResponse(AuthBaseResponse):
    code: int = Field(default=400, description="Status code")
    message: str = Field(default="error", description="Message")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None
