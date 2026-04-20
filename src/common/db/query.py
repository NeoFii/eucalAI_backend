"""Reusable list-query parameter and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class ListParams:
    """Small shared container for list query options."""

    page: int = 1
    page_size: int = 20
    order_by: str | None = None
    order_dir: str = "desc"
    filters: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PaginatedResult(Generic[T]):
    """Simple paginated payload container."""

    items: Sequence[T]
    total: int
    page: int
    page_size: int
