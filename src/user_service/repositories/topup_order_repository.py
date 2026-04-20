"""Top-up order repository."""

from __future__ import annotations

from sqlalchemy import func, select

from common.db import BaseRepository
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

    async def list_for_user(self, *, user_id: int, page: int, page_size: int) -> tuple[list[TopupOrder], int]:
        query = select(TopupOrder).where(TopupOrder.user_id == user_id).order_by(TopupOrder.created_at.desc())
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    async def list_all(
        self,
        *,
        page: int,
        page_size: int,
        user_id: int | None,
        status: int | None,
    ) -> tuple[list[TopupOrder], int]:
        query = select(TopupOrder)
        if user_id is not None:
            query = query.where(TopupOrder.user_id == user_id)
        if status is not None:
            query = query.where(TopupOrder.status == status)
        query = query.order_by(TopupOrder.created_at.desc())
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total
