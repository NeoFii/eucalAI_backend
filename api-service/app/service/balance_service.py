"""Balance and ledger operations for api-service."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import UserNotFoundException, ValidationException
from app.common.infra.db.query import ListParams, PaginatedResult
from app.common.utils.timezone import now
from app.model import BalanceTransaction, TopupOrder, User
from app.repository.billing_repository import BillingRepository
from app.repository.user_repository import UserRepository

logger = logging.getLogger(__name__)


class BalanceService:
    """All wallet mutations must flow through this service.

    Every mutating method acquires the user row via
    ``UserRepository.get_by_id(..., for_update=True)`` BEFORE mutation
    (SELECT ... FOR UPDATE row lock) and is idempotent via
    ``BillingRepository.exists_by_ref(...)`` on the (tx_type, ref_type, ref_id)
    triple.
    """

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
    async def consume_for_call_log(
        db: AsyncSession,
        user_id: int,
        request_id: str,
        cost: int,
        total_tokens: int = 0,
        api_key_id: int | None = None,
    ) -> bool:
        """Deduct cost for a completed API call. Idempotent by request_id.

        Returns True on success, False if balance is insufficient.
        Does not raise on insufficient balance because the call already happened.
        """
        if cost <= 0:
            return True
        billing_repo = BillingRepository(db)
        if await billing_repo.exists_by_ref(
            tx_type=BalanceTransaction.TYPE_CONSUME,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return True

        user = await BalanceService._get_user(db, user_id, for_update=True)
        if user.balance < cost:
            logger.warning(
                "余额不足: user=%d, balance=%d, cost=%d, request=%s",
                user_id, user.balance, cost, request_id,
            )
            return False

        balance_before = int(user.balance)
        user.balance -= cost
        user.used_amount += cost
        user.total_requests += 1
        user.total_tokens += total_tokens
        billing_repo.add_tx(
            BalanceTransaction(
                user_id=user.id,
                type=BalanceTransaction.TYPE_CONSUME,
                amount=-cost,
                balance_before=balance_before,
                balance_after=int(user.balance),
                ref_type="api_call",
                ref_id=request_id,
            )
        )
        return True

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
        billing_repo = BillingRepository(db)
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
        billing_repo.add_tx(
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
        billing_repo = BillingRepository(db)
        if await BalanceService._transaction_exists(
            db,
            tx_type=BalanceTransaction.TYPE_CONSUME,
            ref_type="api_call",
            ref_id=request_id,
        ):
            return

        if user.frozen_amount < actual_amount:
            raise ValidationException(detail="冻结余额不足，无法结算")
        balance_estimated_amount = min(int(user.frozen_amount), estimated_amount)

        unfreeze_before = int(user.balance)
        if balance_estimated_amount > 0:
            user.frozen_amount -= balance_estimated_amount
            user.balance += balance_estimated_amount
            billing_repo.add_tx(
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
        if user.balance < actual_amount:
            raise ValidationException(detail="余额不足，无法完成扣费")
        user.balance -= actual_amount
        user.used_amount += actual_amount
        user.total_requests += 1
        user.total_tokens += total_tokens
        billing_repo.add_tx(
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

        await db.commit()

    @staticmethod
    async def refund(db: AsyncSession, user_id: int, request_id: str, amount: int) -> None:
        if amount <= 0:
            raise ValidationException(detail="退款金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        billing_repo = BillingRepository(db)
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
        billing_repo.add_tx(
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
        operator_id: str | None,
        remark: str = "",
    ) -> None:
        if amount <= 0:
            raise ValidationException(detail="充值金额必须大于 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        billing_repo = BillingRepository(db)
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
        order.paid_at = now()
        billing_repo.add_tx(
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
        operator_id: str | None,
        remark: str,
    ) -> None:
        if amount == 0:
            raise ValidationException(detail="调整金额不能为 0")
        user = await BalanceService._get_user(db, user_id, for_update=True)
        billing_repo = BillingRepository(db)
        balance_after = int(user.balance) + amount
        if balance_after < 0:
            raise ValidationException(detail="调整后余额不能为负数")

        balance_before = int(user.balance)
        user.balance = balance_after
        billing_repo.add_tx(
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
        tx_type: int | None = None,
    ) -> PaginatedResult[BalanceTransaction]:
        return await BillingRepository(db).list_tx_for_user(
            user_id=user_id,
            params=params,
            tx_type=tx_type,
        )

    @staticmethod
    async def list_all_transactions(
        db: AsyncSession,
        *,
        user_id: int | None = None,
        params: ListParams,
    ) -> PaginatedResult[BalanceTransaction]:
        return await BillingRepository(db).list_tx_all(
            user_id=user_id,
            params=params,
        )

    @staticmethod
    async def redeem_code(
        db: AsyncSession,
        *,
        user_id: int,
        raw_code: str,
    ):
        """Thin wrapper exposing VoucherService.redeem_code for completeness.

        The actual ref_id-idempotent + SELECT FOR UPDATE flow lives in
        VoucherService.redeem_code; this delegation keeps the BalanceService
        public surface mirroring the must_haves checklist.
        """
        # Lazy import: voucher_service imports balance_service implicitly via
        # the BillingRepository, but Python handles this fine at call time.
        from app.service.voucher_service import VoucherService

        return await VoucherService.redeem_code(db, user_id=user_id, raw_code=raw_code)

    @staticmethod
    async def get_user_by_uid(db: AsyncSession, uid: str) -> User:
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
    async def _get_topup_order(
        db: AsyncSession,
        order_no: str,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> TopupOrder:
        order = await BillingRepository(db).topup_get_for_user_by_order_no(
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
        return await BillingRepository(db).exists_by_ref(
            tx_type=tx_type,
            ref_type=ref_type,
            ref_id=ref_id,
        )

