"""Balance transaction repository."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository, ListParams, PaginatedResult
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

    async def list_for_user(
        self,
        *,
        user_id: int,
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        if params.order_by is None:
            params.order_by = "created_at"
        return await self.get_list(
            params,
            extra_filters=(BalanceTransaction.user_id == user_id,),
        )

    async def list_all(
        self,
        *,
        user_id: int | None,
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        if params.order_by is None:
            params.order_by = "created_at"
        filters = ()
        if user_id is not None:
            filters = (BalanceTransaction.user_id == user_id,)
        return await self.get_list(params, extra_filters=filters)
