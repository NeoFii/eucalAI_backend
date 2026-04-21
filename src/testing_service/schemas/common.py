"""Common testing-service response schemas."""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None


class ListResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
