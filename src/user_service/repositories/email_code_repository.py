"""Email verification code repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from common.db import BaseRepository
from user_service.models.email_verification_code import EmailVerificationCode


class EmailCodeRepository(BaseRepository[EmailVerificationCode]):
    def __init__(self, session) -> None:
        super().__init__(session, EmailVerificationCode)

    async def count_created_since(self, email: str, purpose: str, created_at_gte: datetime) -> int:
        statement = select(func.count()).select_from(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= created_at_gte,
        )
        return int((await self.session.execute(statement)).scalar() or 0)

    async def latest_for_email(self, email: str, purpose: str) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def latest_unused_for_email(self, email: str, purpose: str) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_unused_for_email(self, email: str, purpose: str) -> list[EmailVerificationCode]:
        statement = select(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used_at.is_(None),
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def delete(self, record: EmailVerificationCode) -> None:
        await self.session.delete(record)
