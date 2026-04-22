"""Voucher lifecycle and billing operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import ValidationException
from common.db import ListParams, PaginatedResult
from common.utils.timezone import now
from user_service.models import UserVoucher, VoucherTransaction
from user_service.repositories import UserVoucherRepository, VoucherTransactionRepository


class VoucherService:
    """Manage user vouchers and voucher billing mutations."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: int,
        amount: int,
        expires_at: datetime | None,
        created_by_admin_uid: int | None,
        remark: str | None = None,
    ) -> UserVoucher:
        if amount <= 0:
            raise ValidationException(detail="代金券金额必须大于 0")
        if expires_at is not None and expires_at <= now():
            raise ValidationException(detail="代金券过期时间必须晚于当前时间")

        voucher = UserVoucher(
            user_id=user_id,
            status=UserVoucher.STATUS_ACTIVE,
            original_amount=amount,
            remaining_amount=amount,
            frozen_amount=0,
            used_amount=0,
            expires_at=expires_at,
            created_by_admin_uid=created_by_admin_uid,
            remark=remark,
        )
        UserVoucherRepository(db).add(voucher)
        await db.flush()
        VoucherTransactionRepository(db).add(
            VoucherTransaction(
                voucher_id=voucher.id,
                user_id=user_id,
                type=VoucherTransaction.TYPE_ISSUE,
                amount=amount,
                balance_before=0,
                balance_after=amount,
                ref_type="admin",
                operator_id=created_by_admin_uid,
                remark=remark,
            )
        )
        await db.commit()
        await db.refresh(voucher)
        return voucher

    @staticmethod
    async def get(db: AsyncSession, voucher_id: int) -> UserVoucher:
        voucher = await UserVoucherRepository(db).get_by_id(voucher_id)
        if voucher is None:
            raise ValidationException(detail="代金券不存在")
        return voucher

    @staticmethod
    async def list_for_admin(
        db: AsyncSession,
        *,
        params: ListParams,
        user_id: int | None = None,
        status: int | None = None,
    ) -> PaginatedResult[UserVoucher]:
        return await UserVoucherRepository(db).list_for_admin(
            params,
            user_id=user_id,
            status=status,
        )

    @staticmethod
    async def update(
        db: AsyncSession,
        *,
        voucher_id: int,
        status: int | None = None,
        expires_at: datetime | None = None,
        remark: str | None = None,
        operator_id: int | None = None,
    ) -> UserVoucher:
        voucher = await VoucherService.get(db, voucher_id)
        if status is not None:
            if status not in {UserVoucher.STATUS_ACTIVE, UserVoucher.STATUS_DISABLED}:
                raise ValidationException(detail="代金券状态无效")
            voucher.status = status
        if expires_at is not None:
            voucher.expires_at = expires_at
        if remark is not None:
            voucher.remark = remark
        VoucherTransactionRepository(db).add(
            VoucherTransaction(
                voucher_id=voucher.id,
                user_id=voucher.user_id,
                type=VoucherTransaction.TYPE_ADMIN_UPDATE,
                amount=0,
                balance_before=int(voucher.remaining_amount),
                balance_after=int(voucher.remaining_amount),
                ref_type="admin",
                operator_id=operator_id,
                remark=remark,
            )
        )
        await db.commit()
        await db.refresh(voucher)
        return voucher

    @staticmethod
    async def delete(
        db: AsyncSession,
        *,
        voucher_id: int,
        operator_id: int | None = None,
    ) -> UserVoucher:
        voucher = await VoucherService.get(db, voucher_id)
        voucher.deleted_at = now()
        voucher.status = UserVoucher.STATUS_DISABLED
        VoucherTransactionRepository(db).add(
            VoucherTransaction(
                voucher_id=voucher.id,
                user_id=voucher.user_id,
                type=VoucherTransaction.TYPE_DELETE,
                amount=0,
                balance_before=int(voucher.remaining_amount),
                balance_after=int(voucher.remaining_amount),
                ref_type="admin",
                operator_id=operator_id,
            )
        )
        await db.commit()
        await db.refresh(voucher)
        return voucher

    @staticmethod
    async def freeze_available(
        db: AsyncSession,
        *,
        user_id: int,
        amount: int,
        request_id: str,
    ) -> int:
        remaining_to_freeze = amount
        frozen_total = 0
        tx_repo = VoucherTransactionRepository(db)
        for voucher in await UserVoucherRepository(db).list_available_for_update(user_id):
            if not isinstance(voucher, UserVoucher):
                continue
            if remaining_to_freeze <= 0:
                break
            freeze_amount = min(int(voucher.remaining_amount), remaining_to_freeze)
            before = int(voucher.remaining_amount)
            voucher.remaining_amount -= freeze_amount
            voucher.frozen_amount += freeze_amount
            tx_repo.add(
                VoucherTransaction(
                    voucher_id=voucher.id,
                    user_id=user_id,
                    type=VoucherTransaction.TYPE_FREEZE,
                    amount=-freeze_amount,
                    balance_before=before,
                    balance_after=int(voucher.remaining_amount),
                    ref_type="api_call",
                    ref_id=request_id,
                )
            )
            remaining_to_freeze -= freeze_amount
            frozen_total += freeze_amount
        return frozen_total

    @staticmethod
    async def settle_frozen(
        db: AsyncSession,
        *,
        user_id: int,
        request_id: str,
        actual_amount: int,
    ) -> int:
        tx_repo = VoucherTransactionRepository(db)
        freeze_txs = await tx_repo.list_by_ref(
            user_id=user_id,
            tx_type=VoucherTransaction.TYPE_FREEZE,
            ref_type="api_call",
            ref_id=request_id,
        )
        remaining_to_consume = actual_amount
        consumed_total = 0
        voucher_repo = UserVoucherRepository(db)

        for freeze_tx in freeze_txs:
            frozen_amount = abs(int(freeze_tx.amount))
            if frozen_amount <= 0:
                continue
            voucher = await voucher_repo.get_by_id(int(freeze_tx.voucher_id), for_update=True)
            if voucher is None:
                continue
            consume_amount = min(frozen_amount, remaining_to_consume)
            release_amount = frozen_amount - consume_amount
            remaining_before = int(voucher.remaining_amount)

            voucher.frozen_amount -= frozen_amount
            voucher.used_amount += consume_amount
            if release_amount:
                voucher.remaining_amount += release_amount

            if consume_amount:
                tx_repo.add(
                    VoucherTransaction(
                        voucher_id=voucher.id,
                        user_id=user_id,
                        type=VoucherTransaction.TYPE_CONSUME,
                        amount=-consume_amount,
                        balance_before=remaining_before,
                        balance_after=int(voucher.remaining_amount),
                        ref_type="api_call",
                        ref_id=request_id,
                    )
                )
                consumed_total += consume_amount
                remaining_to_consume -= consume_amount
            if release_amount:
                tx_repo.add(
                    VoucherTransaction(
                        voucher_id=voucher.id,
                        user_id=user_id,
                        type=VoucherTransaction.TYPE_RELEASE,
                        amount=release_amount,
                        balance_before=remaining_before,
                        balance_after=int(voucher.remaining_amount),
                        ref_type="api_call",
                        ref_id=request_id,
                    )
                )
            if remaining_to_consume <= 0:
                remaining_to_consume = 0

        return consumed_total

    @staticmethod
    async def release_frozen(
        db: AsyncSession,
        *,
        user_id: int,
        request_id: str,
        amount: int,
    ) -> int:
        tx_repo = VoucherTransactionRepository(db)
        freeze_txs = await tx_repo.list_by_ref(
            user_id=user_id,
            tx_type=VoucherTransaction.TYPE_FREEZE,
            ref_type="api_call",
            ref_id=request_id,
        )
        remaining_to_release = amount
        released_total = 0
        voucher_repo = UserVoucherRepository(db)

        for freeze_tx in freeze_txs:
            if remaining_to_release <= 0:
                break
            frozen_amount = abs(int(freeze_tx.amount))
            release_amount = min(frozen_amount, remaining_to_release)
            if release_amount <= 0:
                continue
            voucher = await voucher_repo.get_by_id(int(freeze_tx.voucher_id), for_update=True)
            if voucher is None:
                continue
            before = int(voucher.remaining_amount)
            voucher.frozen_amount -= release_amount
            voucher.remaining_amount += release_amount
            tx_repo.add(
                VoucherTransaction(
                    voucher_id=voucher.id,
                    user_id=user_id,
                    type=VoucherTransaction.TYPE_RELEASE,
                    amount=release_amount,
                    balance_before=before,
                    balance_after=int(voucher.remaining_amount),
                    ref_type="api_call",
                    ref_id=request_id,
                )
            )
            released_total += release_amount
            remaining_to_release -= release_amount
        return released_total
