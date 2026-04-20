"""Top-up order operations for user-service."""

from __future__ import annotations

import secrets
import string

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import ValidationException
from common.utils.timezone import now
from user_service.models import TopupOrder
from user_service.services.balance_service import BalanceService

_ORDER_ALPHABET = string.ascii_uppercase + string.digits


class TopupOrderService:
    """Manage manual top-up orders."""

    @staticmethod
    async def create_manual(
        db: AsyncSession,
        user_id: int,
        amount: int,
        operator_id: int,
        remark: str = "",
    ) -> TopupOrder:
        if amount <= 0:
            raise ValidationException(detail="充值金额必须大于 0")

        order = TopupOrder(
            user_id=user_id,
            amount=amount,
            order_no=TopupOrderService._generate_order_no(),
            status=TopupOrder.STATUS_PENDING,
            payment_channel="manual",
            operator_id=operator_id,
            remark=remark or None,
        )
        db.add(order)
        await db.flush()
        await BalanceService.topup(
            db,
            user_id=user_id,
            amount=amount,
            order_no=order.order_no,
            operator_id=operator_id,
            remark=remark,
        )
        return order

    @staticmethod
    async def get_user_orders(
        db: AsyncSession,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TopupOrder], int]:
        query = select(TopupOrder).where(TopupOrder.user_id == user_id).order_by(TopupOrder.created_at.desc())
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    async def get_all_orders(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
        status: int | None = None,
    ) -> tuple[list[TopupOrder], int]:
        query = select(TopupOrder)
        if user_id is not None:
            query = query.where(TopupOrder.user_id == user_id)
        if status is not None:
            query = query.where(TopupOrder.status == status)
        query = query.order_by(TopupOrder.created_at.desc())
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    def _generate_order_no() -> str:
        return "TP" + now().strftime("%Y%m%d") + "".join(secrets.choice(_ORDER_ALPHABET) for _ in range(8))
