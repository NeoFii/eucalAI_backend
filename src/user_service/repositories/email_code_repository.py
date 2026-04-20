"""Email verification code repository."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository
from user_service.models.email_verification_code import EmailVerificationCode


class EmailCodeRepository(BaseRepository[EmailVerificationCode]):
    def __init__(self, session) -> None:
        super().__init__(session, EmailVerificationCode)

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
