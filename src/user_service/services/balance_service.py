"""Balance and ledger operations for user-service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import UserNotFoundException, ValidationException
from common.db import ListParams, PaginatedResult
from user_service.models import BalanceTransaction, TopupOrder, User, UserApiKey
from user_service.repositories import (
    ApiKeyRepository,
    BalanceTxRepository,
    TopupOrderRepository,
    UserRepository,
)
from user_service.services.voucher_service import VoucherService


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
    async def freeze(
        db: AsyncSession,
        user_id: int,
        amount: int,
        request_id: str,
        api_key_id: int | None = None,
    ) -> None:
        if amount <= 0:
            raise ValidationException(detail="冻结金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        tx_repo = BalanceTxRepository(db)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_FREEZE,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return

        if api_key_id is not None:
            api_key = await BalanceService._get_api_key(db, api_key_id, user.id, for_update=True)
            BalanceService._ensure_api_key_quota(api_key, amount)

        voucher_amount = await VoucherService.freeze_available(
            db,
            user_id=user.id,
            amount=amount,
            request_id=request_id,
        )
        balance_amount = amount - voucher_amount
        if balance_amount <= 0:
            await db.commit()
            return
        if user.balance < balance_amount:
            raise ValidationException(detail="余额不足")

        balance_before = int(user.balance)
        user.balance -= balance_amount
        user.frozen_amount += balance_amount
        tx_repo.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_FREEZE,
                amount=-balance_amount,
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
        tx_repo = BalanceTxRepository(db)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_CONSUME,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return
        api_key = None
        if api_key_id is not None:
            api_key = await BalanceService._get_api_key(db, api_key_id, user.id, for_update=True)
            BalanceService._ensure_api_key_quota(api_key, actual_amount)

        voucher_amount = await VoucherService.settle_frozen(
            db,
            user_id=user.id,
            request_id=request_id,
            actual_amount=actual_amount,
        )
        balance_actual_amount = actual_amount - voucher_amount
        if user.frozen_amount < balance_actual_amount:
            raise ValidationException(detail="冻结余额不足，无法结算")
        balance_estimated_amount = min(
            int(user.frozen_amount),
            max(estimated_amount - voucher_amount, balance_actual_amount),
        )

        unfreeze_before = int(user.balance)
        if balance_estimated_amount > 0:
            user.frozen_amount -= balance_estimated_amount
            user.balance += balance_estimated_amount
            tx_repo.add(
                BalanceTransaction(
                    user_id=user.id,
                    type=BalanceTransaction.TYPE_UNFREEZE,
                    amount=balance_estimated_amount,
                    balance_before=unfreeze_before,
                    balance_after=int(user.balance),
                    ref_type="api_call",
                    ref_id=request_id,
                )
            )

        consume_before = int(user.balance)
        if user.balance < balance_actual_amount:
            raise ValidationException(detail="余额不足，无法完成扣费")
        user.balance -= balance_actual_amount
        user.used_amount += actual_amount
        user.total_requests += 1
        user.total_tokens += total_tokens
        tx_repo.add(
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

        if api_key is not None:
            api_key.quota_used += actual_amount
            if api_key.is_exhausted:
                api_key.status = UserApiKey.STATUS_EXHAUSTED

        await db.commit()

    @staticmethod
    async def refund(db: AsyncSession, user_id: int, request_id: str, amount: int) -> None:
        if amount <= 0:
            raise ValidationException(detail="退款金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        tx_repo = BalanceTxRepository(db)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_REFUND,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return
        voucher_amount = await VoucherService.release_frozen(
            db,
            user_id=user.id,
            request_id=request_id,
            amount=amount,
        )
        balance_amount = amount - voucher_amount
        if balance_amount <= 0:
            await db.commit()
            return
        if user.frozen_amount < balance_amount:
            raise ValidationException(detail="冻结余额不足，无法退款")

        balance_before = int(user.balance)
        user.frozen_amount -= balance_amount
        user.balance += balance_amount
        tx_repo.add(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_REFUND,
                amount=balance_amount,
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
        tx_repo = BalanceTxRepository(db)
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
        tx_repo.add(
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
        tx_repo = BalanceTxRepository(db)
        balance_after = int(user.balance) + amount
        if balance_after < 0:
            raise ValidationException(detail="调整后余额不能为负数")

        balance_before = int(user.balance)
        user.balance = balance_after
        tx_repo.add(
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
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        return await BalanceTxRepository(db).list_for_user(
            user_id=user_id,
            params=params,
        )

    @staticmethod
    async def list_all_transactions(
        db: AsyncSession,
        *,
        user_id: int | None = None,
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        return await BalanceTxRepository(db).list_all(
            user_id=user_id,
            params=params,
        )

    @staticmethod
    async def get_user_by_uid(db: AsyncSession, uid: int) -> User:
        user = await UserRepository(db).get_by_uid(uid)
        if user is None:
            raise UserNotFoundException()
        return user

    @staticmethod
    async def _get_user(db: AsyncSession, user_id: int, *, for_update: bool = False) -> User:
        user = await UserRepository(db).get_by_id(user_id, for_update=for_update)
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
        api_key = await ApiKeyRepository(db).get_owned_key(
            api_key_id,
            user_id,
            for_update=for_update,
        )
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
        order = await TopupOrderRepository(db).get_for_user_by_order_no(
            order_no=order_no,
            user_id=user_id,
            for_update=for_update,
        )
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
        return await BalanceTxRepository(db).exists_by_ref(
            tx_type=tx_type,
            ref_type=ref_type,
            ref_id=ref_id,
        )

    @staticmethod
    def _ensure_api_key_quota(api_key: UserApiKey, amount: int) -> None:
        if api_key.quota_mode != UserApiKey.MODE_LIMITED:
            return
        if int(api_key.quota_used) + amount > int(api_key.quota_limit):
            raise ValidationException(detail="API Key 限额不足")
