"""Top-up order operations for user-service."""

from __future__ import annotations

import logging
import secrets
import string

from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams, PaginatedResult
from common.core.exceptions import ValidationException
from common.observability import log_event
from common.utils.timezone import now
from core.config import settings
from models import TopupOrder
from repositories import TopupOrderRepository
from services.balance_service import BalanceService

_ORDER_ALPHABET = string.ascii_uppercase + string.digits
logger = logging.getLogger(__name__)


class TopupOrderService:
    """Manage top-up orders."""

    @staticmethod
    async def create_manual(
        db: AsyncSession,
        user_id: int,
        amount: int,
        operator_id: str | None = None,
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
        TopupOrderRepository(db).add(order)
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
    async def create_alipay_order(
        db: AsyncSession,
        user_id: int,
        amount: int,
    ) -> TopupOrder:
        if amount < settings.MIN_TOPUP_AMOUNT:
            raise ValidationException(detail="充值金额不能低于最小限额")
        if amount > settings.MAX_TOPUP_AMOUNT:
            raise ValidationException(detail="充值金额不能超过最大限额")

        order = TopupOrder(
            user_id=user_id,
            amount=amount,
            order_no=TopupOrderService._generate_order_no(),
            status=TopupOrder.STATUS_PENDING,
            payment_channel="alipay",
        )
        TopupOrderRepository(db).add(order)
        await db.flush()
        await db.commit()
        log_event(logger, logging.INFO, "alipayOrderCreated", order_no=order.order_no, amount=amount)
        return order

    @staticmethod
    async def mark_paid(
        db: AsyncSession,
        order: TopupOrder,
        payment_no: str,
        payment_raw: dict,
    ) -> None:
        order.payment_no = payment_no
        order.payment_raw = payment_raw
        await BalanceService.topup(
            db,
            user_id=int(order.user_id),
            amount=int(order.amount),
            order_no=order.order_no,
            operator_id=None,
            remark="支付宝充值",
        )
        log_event(
            logger, logging.INFO, "alipayOrderPaid",
            order_no=order.order_no, payment_no=payment_no,
        )

    @staticmethod
    async def cancel_order(db: AsyncSession, order_no: str) -> None:
        repo = TopupOrderRepository(db)
        order = await repo.get_by_order_no(order_no=order_no, for_update=True)
        if order is None or order.status != TopupOrder.STATUS_PENDING:
            return
        order.status = TopupOrder.STATUS_CANCELLED
        await db.commit()

    @staticmethod
    async def get_user_orders(
        db: AsyncSession,
        user_id: int,
        params: ListParams,
    ) -> PaginatedResult[TopupOrder]:
        return await TopupOrderRepository(db).list_for_user(
            user_id=user_id,
            params=params,
        )

    @staticmethod
    async def get_all_orders(
        db: AsyncSession,
        params: ListParams,
        user_id: int | None = None,
        status: int | None = None,
    ) -> PaginatedResult[TopupOrder]:
        return await TopupOrderRepository(db).list_all(
            params=params,
            user_id=user_id,
            status=status,
        )

    @staticmethod
    def _generate_order_no() -> str:
        return "TP" + now().strftime("%Y%m%d") + "".join(secrets.choice(_ORDER_ALPHABET) for _ in range(8))
