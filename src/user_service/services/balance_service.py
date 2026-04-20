"""Balance and ledger operations for user-service."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import UserNotFoundException, ValidationException
from user_service.models import BalanceTransaction, TopupOrder, User, UserApiKey


class BalanceService:
    """All wallet mutations must flow through this service."""

    @staticmethod
    async def get_balance(db: AsyncSession, user_id: int) -> dict:
        user = await BalanceService._get_user(db, user_id)
        return {
            "balance": int(user.balance),
            "frozen_amount": int(user.frozen_amount),
            "used_amount": int(user.used_amount),
            "total_requests": int(user.total_requests),
            "total_tokens": int(user.total_tokens),
        }

    @staticmethod
    async def freeze(db: AsyncSession, user_id: int, amount: int, request_id: str) -> None:
        if amount <= 0:
            raise ValidationException(detail="冻结金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_FREEZE,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return
        if user.balance < amount:
            raise ValidationException(detail="余额不足")

        balance_before = int(user.balance)
        user.balance -= amount
        user.frozen_amount += amount
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_FREEZE,
                amount=-amount,
                balance_before=balance_before,
                balance_after=int(user.balance),
                ref_type="api_call",
                ref_id=request_id,
            )
        )
        await db.commit()

    @staticmethod
    async def settle(
        db: AsyncSession,
        user_id: int,
        request_id: str,
        estimated_amount: int,
        actual_amount: int,
        api_key_id: int | None = None,
        total_tokens: int = 0,
    ) -> None:
        if estimated_amount <= 0 or actual_amount < 0:
            raise ValidationException(detail="结算金额无效")
        if actual_amount > estimated_amount:
            raise ValidationException(detail="实际结算金额不能超过冻结金额")

        user = await BalanceService._get_user(db, user_id, for_update=True)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_CONSUME,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return
        if user.frozen_amount < estimated_amount:
            raise ValidationException(detail="冻结余额不足，无法结算")

        unfreeze_before = int(user.balance)
        user.frozen_amount -= estimated_amount
        user.balance += estimated_amount
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_UNFREEZE,
                amount=estimated_amount,
                balance_before=unfreeze_before,
                balance_after=int(user.balance),
                ref_type="api_call",
                ref_id=request_id,
            )
        )

        consume_before = int(user.balance)
        if user.balance < actual_amount:
            raise ValidationException(detail="余额不足，无法完成扣费")
        user.balance -= actual_amount
        user.used_amount += actual_amount
        user.total_requests += 1
        user.total_tokens += total_tokens
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_CONSUME,
                amount=-actual_amount,
                balance_before=consume_before,
                balance_after=int(user.balance),
                ref_type="api_call",
                ref_id=request_id,
            )
        )

        if api_key_id is not None:
            api_key = await BalanceService._get_api_key(db, api_key_id, user.id, for_update=True)
            api_key.quota_used += actual_amount
            if api_key.is_exhausted:
                api_key.status = UserApiKey.STATUS_EXHAUSTED

        await db.commit()

    @staticmethod
    async def refund(db: AsyncSession, user_id: int, request_id: str, amount: int) -> None:
        if amount <= 0:
            raise ValidationException(detail="退款金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_REFUND,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return
        if user.frozen_amount < amount:
            raise ValidationException(detail="冻结余额不足，无法退款")

        balance_before = int(user.balance)
        user.frozen_amount -= amount
        user.balance += amount
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_REFUND,
                amount=amount,
                balance_before=balance_before,
                balance_after=int(user.balance),
                ref_type="api_call",
                ref_id=request_id,
            )
        )
        await db.commit()

    @staticmethod
    async def topup(
        db: AsyncSession,
        user_id: int,
        amount: int,
        order_no: str,
        operator_id: int | None,
        remark: str = "",
    ) -> None:
        if amount <= 0:
            raise ValidationException(detail="充值金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        order = await BalanceService._get_topup_order(db, order_no, user.id, for_update=True)
        if order.status != TopupOrder.STATUS_PENDING:
            raise ValidationException(detail="充值订单状态无效")
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_TOPUP,
            ref_type="topup_order",
            ref_id=order_no,
        ):
            return

        balance_before = int(user.balance)
        user.balance += amount
        order.status = TopupOrder.STATUS_PAID
        from common.utils.timezone import now

        order.paid_at = now()
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_TOPUP,
                amount=amount,
                balance_before=balance_before,
                balance_after=int(user.balance),
                ref_type="topup_order",
                ref_id=order_no,
                operator_id=operator_id,
                remark=remark or None,
            )
        )
        await db.commit()

    @staticmethod
    async def admin_adjust(
        db: AsyncSession,
        user_id: int,
        amount: int,
        operator_id: int,
        remark: str,
    ) -> None:
        if amount == 0:
            raise ValidationException(detail="调整金额不能为 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        balance_after = int(user.balance) + amount
        if balance_after < 0:
            raise ValidationException(detail="调整后余额不能为负数")

        balance_before = int(user.balance)
        user.balance = balance_after
        db.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_ADMIN_ADJUST,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                operator_id=operator_id,
                remark=remark or None,
            )
        )
        await db.commit()

    @staticmethod
    async def list_transactions(
        db: AsyncSession,
        *,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BalanceTransaction], int]:
        query = select(BalanceTransaction).where(BalanceTransaction.user_id == user_id).order_by(
            BalanceTransaction.created_at.desc()
        )
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    async def list_all_transactions(
        db: AsyncSession,
        *,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BalanceTransaction], int]:
        query = select(BalanceTransaction)
        if user_id is not None:
            query = query.where(BalanceTransaction.user_id == user_id)
        query = query.order_by(BalanceTransaction.created_at.desc())
        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0)
        items = list((await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return items, total

    @staticmethod
    async def get_user_by_uid(db: AsyncSession, uid: int) -> User:
        user = (await db.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
        if user is None:
            raise UserNotFoundException()
        return user

    @staticmethod
    async def _get_user(db: AsyncSession, user_id: int, *, for_update: bool = False) -> User:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        user = (await db.execute(statement)).scalar_one_or_none()
        if user is None:
            raise UserNotFoundException()
        return user

    @staticmethod
    async def _get_api_key(
        db: AsyncSession,
        api_key_id: int,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> UserApiKey:
        statement = select(UserApiKey).where(
            UserApiKey.id == api_key_id,
            UserApiKey.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        api_key = (
            await db.execute(statement)
        ).scalar_one_or_none()
        if api_key is None:
            raise ValidationException(detail="API Key 不存在")
        return api_key

    @staticmethod
    async def _get_topup_order(
        db: AsyncSession,
        order_no: str,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> TopupOrder:
        statement = select(TopupOrder).where(
            TopupOrder.order_no == order_no,
            TopupOrder.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        order = (
            await db.execute(statement)
        ).scalar_one_or_none()
        if order is None:
            raise ValidationException(detail="充值订单不存在")
        return order

    @staticmethod
    async def _transaction_exists(
        db: AsyncSession,
        *,
        tx_type: int,
        ref_type: str,
        ref_id: str,
    ) -> bool:
        existing = (
            await db.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.type == tx_type,
                    BalanceTransaction.ref_type == ref_type,
                    BalanceTransaction.ref_id == ref_id,
                )
            )
        ).scalar_one_or_none()
        return isinstance(existing, BalanceTransaction)
