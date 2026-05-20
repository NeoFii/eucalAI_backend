"""Admin voucher service — proxy elimination wrapper.

Wraps Phase 4 VoucherService with admin-perspective shape.
Class name: AdminVoucherService (NOT VoucherService — Pitfall 3).
D-02a: no acting_admin_id parameter passed into Phase 4 service.
Warning 5: method names verified against Phase 4 source.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.infra.db.query import ListParams
from app.service.voucher_service import VoucherService


class AdminVoucherService:
    """Wraps Phase 4 VoucherService with admin-perspective shape."""

    @staticmethod
    async def generate_codes(
        db: AsyncSession,
        *,
        amount: int,
        count: int,
        starts_at: datetime,
        expires_at: datetime,
        operator_admin_uid: str,
        remark: str | None = None,
    ) -> list:
        return await VoucherService.generate_codes(
            db,
            amount=amount,
            count=count,
            starts_at=starts_at,
            expires_at=expires_at,
            created_by_admin_uid=operator_admin_uid,
            remark=remark,
        )

    @staticmethod
    async def list_codes(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: int | None = None,
    ) -> tuple[list, int]:
        # Warning 5: method is list_codes (NOT bare list)
        result = await VoucherService.list_for_admin(
            db,
            params=ListParams(page=page, page_size=page_size),
            status=status,
        )
        return result.items, result.total

    @staticmethod
    async def get(db: AsyncSession, *, code_id: int):
        return await VoucherService.get(db, code_id=code_id)

    @staticmethod
    async def disable(db: AsyncSession, *, code_id: int, operator_uid: str | None = None):
        return await VoucherService.disable(db, code_id=code_id, operator_id=operator_uid)


__all__ = ["AdminVoucherService"]
