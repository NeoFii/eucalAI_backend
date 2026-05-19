"""Unified shared schema primitives for api-service (D-04 hoist).

This module is the single source of truth for the cross-domain response
envelope primitives (`BaseResponse`, `ErrorResponse`, `DateTimeModel`,
`ApiResponse[T]`). It replaces the per-domain duplicates that used to live in
user-service and admin-service `schemas/common.py` (both removed under D-04).

Plan 05-01 / Task 1a:
    • New file (D-04 hoist).
    • Phase 4 imports rewritten: the legacy per-domain schemas-common path is
      replaced with `from api_service.common.schemas import ...`, and legacy
      per-domain envelope names renamed to the unified `BaseResponse`/
      `ErrorResponse`.

Pitfall 7 (load-bearing): `DateTimeModel.serialize_model` MUST iterate over
`list(data.items())` rather than `data.items()`. The wrap creates a snapshot
of the dict so that re-assigning entries inside the loop does not invalidate
the iterator. Do NOT lint-clean this — it is the runtime-safety preserve.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field, model_serializer

from api_service.common.utils.timezone import format_iso

T = TypeVar("T")


class DateTimeModel(BaseModel):
    """Pydantic mixin that serializes `datetime` fields as ISO-8601 strings."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        # Pitfall 7 (CRITICAL): iterate over list(data.items()) copy so that
        # mutating data[key] does not invalidate the iterator. Do NOT lint-clean.
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class BaseResponse(BaseModel):
    """Canonical success envelope for both user and admin domains.

    Unified replacement for the deprecated per-domain envelope classes that
    used to live in user-service and admin-service `schemas/common.py`. See
    D-04 + Pitfall 8.
    """

    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")


class ErrorResponse(BaseResponse):
    """Canonical error envelope (overrides defaults to 400 / "error")."""

    code: int = Field(default=400, description="Error code")
    message: str = Field(default="error", description="Error message")


class ApiResponse(BaseModel, Generic[T]):
    """Generic envelope used when the payload type varies (`ApiResponse[Foo]`)."""

    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None


__all__ = [
    "ApiResponse",
    "BaseResponse",
    "DateTimeModel",
    "ErrorResponse",
]
