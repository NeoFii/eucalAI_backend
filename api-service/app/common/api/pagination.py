"""Shared paginated response schema."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.common.infra.db.query import PaginatedResult

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Canonical API schema for paginated payloads."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_result(cls, result: PaginatedResult[T]) -> "PaginatedResponse[T]":
        return cls(
            items=list(result.items),
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )
