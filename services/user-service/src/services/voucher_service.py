"""Voucher redemption-code lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import UserNotFoundException, ValidationException
from common.db import ListParams, PaginatedResult
from common.utils.timezone import now, to_shanghai_naive
from models import BalanceTransaction, VoucherRedemptionCode
from repositories import (
    BalanceTxRepository,
    UserRepository,
    VoucherRedemptionCodeRepository,
)


@dataclass(slots=True)
class GeneratedVoucherCode:
    code: str
    record: VoucherRedemptionCode


class VoucherService:
    """Manage system-generated voucher redemption codes."""

    @staticmethod
    def normalize_code(raw_code: str) -> str:
        return raw_code.strip().lower()

    @staticmethod
    def hash_code(raw_code: str) -> str:
        normalized = VoucherService.normalize_code(raw_code)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_plain_code() -> str:
        return uuid.uuid4().hex

    @staticmethod
    async def generate_codes(
        db: AsyncSession,
        *,
        amount: int,
        count: int,
        starts_at: datetime,
        expires_at: datetime,
        created_by_admin_uid: str | None,
        remark: str | None = None,
    ) -> list[GeneratedVoucherCode]:
        if amount <= 0:
            raise ValidationException(detail="代金券金额必须大于 0")
        if count <= 0:
            raise ValidationException(detail="生成数量必须大于 0")
        if count > 1000:
            raise ValidationException(detail="单次最多生成 1000 个兑换码")
        starts_at = to_shanghai_naive(starts_at)
        expires_at = to_shanghai_naive(expires_at)
        if starts_at >= expires_at:
            raise ValidationException(detail="开始时间必须早于过期时间")

        repo = VoucherRedemptionCodeRepository(db)
        generated: list[GeneratedVoucherCode] = []
        seen_hashes: set[str] = set()
        while len(generated) < count:
            plain_code = VoucherService._generate_plain_code()
            code_hash = VoucherService.hash_code(plain_code)
            if code_hash in seen_hashes:
                continue
            seen_hashes.add(code_hash)
            record = VoucherRedemptionCode(
                code_hash=code_hash,
                code_prefix=plain_code[:4],
                code_suffix=plain_code[-4:],
                amount=amount,
                status=VoucherRedemptionCode.STATUS_ACTIVE,
                starts_at=starts_at,
                expires_at=expires_at,
                created_by_admin_uid=created_by_admin_uid,
                remark=remark,
            )
            repo.add(record)
            generated.append(GeneratedVoucherCode(code=plain_code, record=record))

        await db.flush()
        await db.commit()
        return generated

    @staticmethod
    async def get(db: AsyncSession, code_id: int) -> VoucherRedemptionCode:
        code = await VoucherRedemptionCodeRepository(db).get_by_id(code_id)
        if code is None:
            raise ValidationException(detail="代金券兑换码不存在")
        return code

    @staticmethod
    async def list_for_admin(
        db: AsyncSession,
        *,
        params: ListParams,
        status: int | None = None,
    ) -> PaginatedResult[VoucherRedemptionCode]:
        return await VoucherRedemptionCodeRepository(db).list_for_admin(params, status=status)

    @staticmethod
    async def list_user_redemptions(
        db: AsyncSession,
        *,
        user_id: int,
        params: ListParams,
    ) -> PaginatedResult[VoucherRedemptionCode]:
        return await VoucherRedemptionCodeRepository(db).list_for_user_redemptions(
            user_id=user_id,
            params=params,
        )

    @staticmethod
    async def disable(
        db: AsyncSession,
        *,
        code_id: int,
        operator_id: str | None = None,
    ) -> VoucherRedemptionCode:
        _ = operator_id
        code = await VoucherRedemptionCodeRepository(db).get_by_id(code_id, for_update=True)
        if code is None:
            raise ValidationException(detail="代金券兑换码不存在")
        if code.status == VoucherRedemptionCode.STATUS_REDEEMED:
            raise ValidationException(detail="已兑换的代金券兑换码不能禁用")
        code.status = VoucherRedemptionCode.STATUS_DISABLED
        await db.commit()
        await db.refresh(code)
        return code

    @staticmethod
    async def redeem_code(
        db: AsyncSession,
        *,
        user_id: int,
        raw_code: str,
        redeemed_at: datetime | None = None,
    ) -> VoucherRedemptionCode:
        redeemed_at = to_shanghai_naive(redeemed_at) or now()
        code_hash = VoucherService.hash_code(raw_code)
        code_repo = VoucherRedemptionCodeRepository(db)
        code = await code_repo.get_by_hash(code_hash, for_update=True)
        if code is None:
            raise ValidationException(detail="代金券兑换码不存在")
        if code.status != VoucherRedemptionCode.STATUS_ACTIVE:
            raise ValidationException(detail="代金券兑换码不可用")
        if redeemed_at < code.starts_at:
            raise ValidationException(detail="代金券兑换码尚未生效")
        if redeemed_at >= code.expires_at:
            raise ValidationException(detail="代金券兑换码已过期")

        user = await UserRepository(db).get_by_id(user_id, for_update=True)
        if user is None:
            raise UserNotFoundException()

        balance_before = int(user.balance)
        user.balance += int(code.amount)
        code.status = VoucherRedemptionCode.STATUS_REDEEMED
        code.redeemed_user_id = user_id
        code.redeemed_at = redeemed_at
        BalanceTxRepository(db).add(
            BalanceTransaction(
                user_id=user_id,
                type=BalanceTransaction.TYPE_VOUCHER_REDEEM,
                amount=int(code.amount),
                balance_before=balance_before,
                balance_after=int(user.balance),
                ref_type="voucher_code",
                ref_id=str(code.id),
                operator_id=code.created_by_admin_uid,
                remark=code.remark,
            )
        )
        await db.commit()
        await db.refresh(code)
        return code
