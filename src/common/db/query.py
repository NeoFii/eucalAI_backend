"""Reusable list-query parameter and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Generic, Sequence, TypeVar

from common.core.exceptions import ValidationException

T = TypeVar("T")


@dataclass(slots=True)
class ListParams:
    """Small shared container for list query options."""

    page: int = 1
    page_size: int = 20
    order_by: str | None = None
    order_dir: str = "desc"
    time_field: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    max_span_days: int = 90
    filters: dict[str, object] = field(default_factory=dict)

    def validate_time_range(
        self,
        *,
        default_end: datetime | None = None,
        default_days: int = 30,
    ) -> tuple[datetime, datetime] | tuple[None, None]:
        if self.time_field is None:
            return None, None

        effective_end = self.end or default_end or datetime.now(timezone.utc)
        effective_start = self.start or (effective_end - timedelta(days=default_days))
        if effective_start >= effective_end:
            raise ValidationException(detail="开始时间必须早于结束时间")
        if effective_end - effective_start > timedelta(days=self.max_span_days):
            raise ValidationException(detail=f"时间范围不能超过 {self.max_span_days} 天")
        self.start = effective_start
        self.end = effective_end
        return effective_start, effective_end


@dataclass(slots=True)
class PaginatedResult(Generic[T]):
    """Simple paginated payload container."""

    items: Sequence[T]
    total: int
    page: int
    page_size: int
