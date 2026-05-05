"""Minimal shared repository base."""

from __future__ import annotations

from typing import Any, Generic, Iterable, Sequence, TypeVar

from sqlalchemy import asc, desc, func, select

from common.db.query import ListParams, PaginatedResult

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Store the session and model class for derived repositories."""

    def __init__(self, session, model: type[ModelT] | None = None) -> None:
        self.session = session
        self.model = model

    def _base_query(self):
        if self.model is None:
            raise ValueError("BaseRepository requires a model for query helpers")
        statement = select(self.model)
        deleted_at = getattr(self.model, "deleted_at", None)
        if deleted_at is not None:
            statement = statement.where(deleted_at.is_(None))
        return statement

    def add(self, instance: ModelT) -> None:
        self.session.add(instance)

    async def find_one(self, *filters) -> ModelT | None:
        return (
            await self.session.execute(self._base_query().where(*filters))
        ).scalar_one_or_none()

    async def get_list(
        self,
        params: ListParams,
        *,
        extra_filters: Iterable | None = None,
        options: Sequence[Any] | None = None,
    ) -> PaginatedResult[ModelT]:
        statement = self._base_query()
        if extra_filters:
            statement = statement.where(*tuple(extra_filters))

        if options:
            for opt in options:
                statement = statement.options(opt)

        if params.time_field is not None:
            start, end = params.validate_time_range()
            time_column = getattr(self.model, params.time_field)
            statement = statement.where(time_column >= start, time_column < end)

        for key, value in params.filters.items():
            if value is None:
                continue
            statement = statement.where(getattr(self.model, key) == value)

        if params.order_by:
            order_column = getattr(self.model, params.order_by)
            order_fn = asc if params.order_dir.lower() == "asc" else desc
            statement = statement.order_by(order_fn(order_column))

        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar() or 0)

        offset = (params.page - 1) * params.page_size
        rows = await self.session.execute(statement.offset(offset).limit(params.page_size))
        return PaginatedResult(
            items=list(rows.scalars().unique().all()),
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
