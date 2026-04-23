"""Data access for voucher redemption codes."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository, ListParams, PaginatedResult
from user_service.models import VoucherRedemptionCode


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
        statement = select(VoucherRedemptionCode).where(VoucherRedemptionCode.id == code_id)
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
        return await self.get_list(params, extra_filters=filters)

    async def list_for_user_redemptions(
        self,
        *,
        user_id: int,
        params: ListParams,
    ) -> PaginatedResult[VoucherRedemptionCode]:
        if params.order_by is None:
            params.order_by = "redeemed_at"
        return await self.get_list(
            params,
            extra_filters=(
                VoucherRedemptionCode.redeemed_user_id == user_id,
                VoucherRedemptionCode.status == VoucherRedemptionCode.STATUS_REDEEMED,
            ),
        )
