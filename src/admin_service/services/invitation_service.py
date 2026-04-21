"""Invitation-code service owned by the admin domain."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.models import InvitationCode
from admin_service.repositories import InvitationCodeRepository
from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
)
from common.utils.timezone import now


class InvitationCodeService:
    """Core invitation-code lifecycle operations."""

    @staticmethod
    def generate_code(length: int = 16) -> str:
        """Generate a secure random invitation code."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    async def generate(
        db: AsyncSession,
        created_by: int,
        quantity: int = 1,
        expires_days: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        max_uses: int = 1,
        remark: Optional[str] = None,
    ) -> list[InvitationCode]:
        """Create one or more invitation codes."""
        del max_uses

        codes: list[InvitationCode] = []
        resolved_expires_at = expires_at or now() + timedelta(days=expires_days or 7)
        repo = InvitationCodeRepository(db)

        for _ in range(quantity):
            code_str = InvitationCodeService.generate_code()
            while await repo.get_by_code(code_str):
                code_str = InvitationCodeService.generate_code()

            code = InvitationCode(
                code=code_str,
                status=0,
                created_by=created_by,
                expires_at=resolved_expires_at,
                remark=remark,
            )
            repo.add(code)
            codes.append(code)

        await db.commit()
        for code in codes:
            await db.refresh(code)
        return codes

    @staticmethod
    async def get_by_code(db: AsyncSession, code: str) -> InvitationCode | None:
        """Look up an invitation code by its raw code value."""
        return await InvitationCodeRepository(db).get_by_code(code)

    @staticmethod
    async def verify_and_use(
        db: AsyncSession,
        code: str,
        used_by: int,
        *,
        commit: bool = True,
    ) -> InvitationCode:
        """Validate an invitation code and mark it as consumed."""
        invitation_code = await InvitationCodeRepository(db).get_by_code(code, for_update=True)

        if invitation_code is None:
            raise InvalidInvitationCodeException()
        if invitation_code.is_used:
            raise InvitationCodeUsedException()
        if invitation_code.is_disabled:
            raise InvitationCodeDisabledException()
        if invitation_code.is_expired:
            raise InvitationCodeExpiredException()

        invitation_code.status = 1
        invitation_code.used_by = used_by
        invitation_code.used_at = now()

        await db.flush()
        if commit:
            await db.commit()
            await db.refresh(invitation_code)
        return invitation_code

    @staticmethod
    async def release(
        db: AsyncSession,
        code: str,
        used_by: int,
        *,
        commit: bool = True,
    ) -> bool:
        """Release a previously consumed invitation code for compensation flows."""
        invitation_code = await InvitationCodeRepository(db).get_by_code(code, for_update=True)
        if invitation_code is None:
            raise InvalidInvitationCodeException()

        if invitation_code.status != 1:
            return False
        if invitation_code.used_by != used_by:
            return False

        invitation_code.status = 0
        invitation_code.used_by = None
        invitation_code.used_at = None
        await db.flush()
        if commit:
            await db.commit()
            await db.refresh(invitation_code)
        return True

    @staticmethod
    async def enable(db: AsyncSession, code_id: int) -> InvitationCode:
        """Enable an unused invitation code."""
        code = await InvitationCodeRepository(db).get_by_id(code_id)

        if code is None:
            raise InvalidInvitationCodeException()
        if code.status == 1:
            raise InvitationCodeUsedException()

        code.status = 0
        await db.commit()
        await db.refresh(code)
        return code

    @staticmethod
    async def disable(db: AsyncSession, code_id: int) -> InvitationCode:
        """Disable an invitation code."""
        code = await InvitationCodeRepository(db).get_by_id(code_id)

        if code is None:
            raise InvalidInvitationCodeException()

        code.status = 2
        await db.commit()
        await db.refresh(code)
        return code

    @staticmethod
    async def update(
        db: AsyncSession,
        code_id: int,
        expires_at: Optional[datetime] = None,
        remark: Optional[str] = None,
    ) -> InvitationCode:
        """Update editable invitation-code fields."""
        code = await InvitationCodeRepository(db).get_by_id(code_id)

        if code is None:
            raise InvalidInvitationCodeException()
        if code.status == 1:
            raise InvitationCodeUsedException()

        if expires_at is not None:
            code.expires_at = expires_at
        if remark is not None:
            code.remark = remark

        await db.commit()
        await db.refresh(code)
        return code

    @staticmethod
    async def list(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[int] = None,
    ) -> tuple[list[InvitationCode], int]:
        """List invitation codes for the control plane."""
        return await InvitationCodeRepository(db).list_codes(
            page=page,
            page_size=page_size,
            status=status,
        )

    @staticmethod
    async def get_stats(db: AsyncSession) -> dict[str, int]:
        """Return invitation-code summary counts."""
        return await InvitationCodeRepository(db).get_stats()
