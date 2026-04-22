"""Data access for user vouchers."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository, ListParams, PaginatedResult
from common.utils.timezone import now
from user_service.models import UserVoucher, VoucherTransaction


class UserVoucherRepository(BaseRepository[UserVoucher]):
    """Repository for user-owned vouchers."""

    def __init__(self, session) -> None:
        super().__init__(session, UserVoucher)

    def _base_query(self):
        return select(UserVoucher).where(UserVoucher.deleted_at.is_(None))

    def add(self, voucher: UserVoucher) -> None:
        self.session.add(voucher)

    async def get_by_id(self, voucher_id: int, *, for_update: bool = False) -> UserVoucher | None:
        statement = self._base_query().where(UserVoucher.id == voucher_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_available_for_update(self, user_id: int) -> list[UserVoucher]:
        statement = (
            self._base_query()
            .where(
                UserVoucher.user_id == user_id,
                UserVoucher.status == UserVoucher.STATUS_ACTIVE,
                UserVoucher.remaining_amount > 0,
                (UserVoucher.expires_at.is_(None)) | (UserVoucher.expires_at > now()),
            )
            .order_by(UserVoucher.expires_at.is_(None), UserVoucher.expires_at.asc(), UserVoucher.created_at.asc())
            .with_for_update()
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_for_admin(
        self,
        params: ListParams,
        *,
        user_id: int | None = None,
        status: int | None = None,
    ) -> PaginatedResult[UserVoucher]:
        filters = []
        if user_id is not None:
            filters.append(UserVoucher.user_id == user_id)
        if status is not None:
            filters.append(UserVoucher.status == status)
        if params.order_by is None:
            params.order_by = "created_at"
        return await self.get_list(params, extra_filters=filters)


class VoucherTransactionRepository(BaseRepository[VoucherTransaction]):
    """Repository for voucher ledger rows."""

    def __init__(self, session) -> None:
        super().__init__(session, VoucherTransaction)

    def add(self, tx: VoucherTransaction) -> None:
        self.session.add(tx)

    async def list_by_ref(
        self,
        *,
        user_id: int,
        tx_type: int,
        ref_type: str,
        ref_id: str,
    ) -> list[VoucherTransaction]:
        rows = await self.session.execute(
            select(VoucherTransaction)
            .where(
                VoucherTransaction.user_id == user_id,
                VoucherTransaction.type == tx_type,
                VoucherTransaction.ref_type == ref_type,
                VoucherTransaction.ref_id == ref_id,
            )
            .order_by(VoucherTransaction.created_at.asc(), VoucherTransaction.id.asc())
        )
        return list(rows.scalars().all())

    async def exists_by_ref(self, *, tx_type: int, ref_type: str, ref_id: str) -> bool:
        existing = (
            await self.session.execute(
                select(VoucherTransaction).where(
                    VoucherTransaction.type == tx_type,
                    VoucherTransaction.ref_type == ref_type,
                    VoucherTransaction.ref_id == ref_id,
                )
            )
        ).scalar_one_or_none()
        return isinstance(existing, VoucherTransaction)
