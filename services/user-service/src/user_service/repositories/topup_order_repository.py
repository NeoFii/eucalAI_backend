"""Top-up order repository."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository, ListParams, PaginatedResult
from user_service.models import TopupOrder


class TopupOrderRepository(BaseRepository[TopupOrder]):
    def __init__(self, session) -> None:
        super().__init__(session, TopupOrder)

    def add(self, order: TopupOrder) -> None:
        self.session.add(order)

    async def get_for_user_by_order_no(
        self,
        *,
        order_no: str,
        user_id: int,
        for_update: bool = False,
    ) -> TopupOrder | None:
        statement = select(TopupOrder).where(
            TopupOrder.order_no == order_no,
            TopupOrder.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_for_user(self, *, user_id: int, params: ListParams) -> PaginatedResult[TopupOrder]:
        if params.order_by is None:
            params.order_by = "created_at"
        return await self.get_list(params, extra_filters=(TopupOrder.user_id == user_id,))

    async def list_all(
        self,
        *,
        params: ListParams,
        user_id: int | None,
        status: int | None,
    ) -> PaginatedResult[TopupOrder]:
        filters = []
        if user_id is not None:
            filters.append(TopupOrder.user_id == user_id)
        if status is not None:
            filters.append(TopupOrder.status == status)
        if params.order_by is None:
            params.order_by = "created_at"
        return await self.get_list(params, extra_filters=tuple(filters))
