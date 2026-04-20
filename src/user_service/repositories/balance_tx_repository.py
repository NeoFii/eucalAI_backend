"""Balance transaction repository."""

from __future__ import annotations

from sqlalchemy import func, select

from common.db import BaseRepository
from user_service.models import BalanceTransaction


class BalanceTxRepository(BaseRepository[BalanceTransaction]):
    def __init__(self, session) -> None:
        super().__init__(session, BalanceTransaction)

    def add(self, tx: BalanceTransaction) -> None:
        self.session.add(tx)

    async def exists_by_ref(self, *, tx_type: int, ref_type: str, ref_id: str) -> bool:
        existing = (
            await self.session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.type == tx_type,
                    BalanceTransaction.ref_type == ref_type,
                    BalanceTransaction.ref_id == ref_id,
                )
            )
        ).scalar_one_or_none()
        return isinstance(existing, BalanceTransaction)

    async def list_for_user(self, *, user_id: int, page: int, page_size: int) -> tuple[list[BalanceTransaction], int]:
        query = select(BalanceTransaction).where(BalanceTransaction.user_id == user_id).order_by(
            BalanceTransaction.created_at.desc()
        )
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    async def list_all(
        self,
        *,
        user_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BalanceTransaction], int]:
        query = select(BalanceTransaction)
        if user_id is not None:
            query = query.where(BalanceTransaction.user_id == user_id)
        query = query.order_by(BalanceTransaction.created_at.desc())
        total = int((await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await self.session.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total
