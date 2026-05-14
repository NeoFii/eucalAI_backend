"""Data access for voucher redemption codes."""

from __future__ import annotations

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import selectinload

from common.db import BaseRepository, ListParams, PaginatedResult
from models import VoucherRedemptionCode


class VoucherRedemptionCodeRepository(BaseRepository[VoucherRedemptionCode]):
    """Repository for hash-only voucher redemption codes."""

    def __init__(self, session) -> None:
        super().__init__(session, VoucherRedemptionCode)

    def add(self, code: VoucherRedemptionCode) -> None:
        self.session.add(code)

    async def get_by_id(
        self,
        code_id: int,
        *,
        for_update: bool = False,
    ) -> VoucherRedemptionCode | None:
        statement = (
            select(VoucherRedemptionCode)
            .options(selectinload(VoucherRedemptionCode.redeemed_user))
            .where(VoucherRedemptionCode.id == code_id)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_hash(
        self,
        code_hash: str,
        *,
        for_update: bool = False,
    ) -> VoucherRedemptionCode | None:
        statement = select(VoucherRedemptionCode).where(VoucherRedemptionCode.code_hash == code_hash)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_for_admin(
        self,
        params: ListParams,
        *,
        status: int | None = None,
    ) -> PaginatedResult[VoucherRedemptionCode]:
        filters = []
        if status is not None:
            filters.append(VoucherRedemptionCode.status == status)
        statement = select(VoucherRedemptionCode).options(
            selectinload(VoucherRedemptionCode.redeemed_user)
        )
        if filters:
            statement = statement.where(*filters)

        if params.order_by:
            order_column = getattr(VoucherRedemptionCode, params.order_by)
            order_fn = asc if params.order_dir.lower() == "asc" else desc
            statement = statement.order_by(order_fn(order_column))

        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar() or 0)

        offset = (params.page - 1) * params.page_size
        rows = await self.session.execute(statement.offset(offset).limit(params.page_size))
        return PaginatedResult(
            items=list(rows.scalars().all()),
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_for_user_redemptions(
        self,
        *,
        user_id: int,
        params: ListParams,
    ) -> PaginatedResult[VoucherRedemptionCode]:
        if params.order_by is None:
            params.order_by = "redeemed_at"

        statement = (
            select(VoucherRedemptionCode)
            .options(selectinload(VoucherRedemptionCode.redeemed_user))
            .where(
                VoucherRedemptionCode.redeemed_user_id == user_id,
                VoucherRedemptionCode.status == VoucherRedemptionCode.STATUS_REDEEMED,
            )
        )

        order_column = getattr(VoucherRedemptionCode, params.order_by)
        order_fn = asc if params.order_dir.lower() == "asc" else desc
        statement = statement.order_by(order_fn(order_column))

        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar() or 0)

        offset = (params.page - 1) * params.page_size
        rows = await self.session.execute(statement.offset(offset).limit(params.page_size))
        return PaginatedResult(
            items=list(rows.scalars().all()),
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
