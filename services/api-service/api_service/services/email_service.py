"""Email verification service for api-service user domain.

D-02 divergence: SMTP send is moved out of the request path. `send_verification_code`
writes the code row + commits, then enqueues an ARQ job. The actual SMTP send
happens inside `api_service.core.jobs.send_verification_email` (worker process).

D-11 divergence: preserve the inner `await db.commit()` in `get_valid_code_or_raise`
verbatim from source so the error-count update lands even when the surrounding
controller rolls back (1:1 source parity).

Pitfall 4 (class vs module-singleton): EmailService has NO `__init__` and NO
module-level `email_service = EmailService()` — all methods are @staticmethod and
callers use `EmailService.X(...)`.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
    CodeExpiredException,
    CodeNotFoundException,
    InvalidCodeException,
)
from api_service.common.observability import log_event
from api_service.common.security.password import hash_password_async, verify_password_async
from api_service.common.utils.email import normalize_email
from api_service.common.utils.timezone import now
from api_service.core.arq_pool import get_arq_pool
from api_service.core.config import settings
from api_service.models import EmailVerificationCode
from api_service.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Pitfall 9: this string MUST equal the function's `__name__` registered in
# WorkerSettings.functions (see core/jobs.py `send_verification_email`).
_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"


class EmailService:
    """Create, verify, and dispatch user email codes."""

    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    async def send_verification_code(
        db: AsyncSession,
        email: str,
        purpose: str = "register",
    ) -> tuple[bool, str]:
        """Write a verification code row + enqueue an ARQ send job (D-02).

        Returns (ok, message). On rate-limit / lockout returns (False, reason).
        On success returns (True, "queued").
        """
        email = normalize_email(email)
        repo = UserRepository(db)
        today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        count = await repo.email_code_count_created_since(email, purpose, today_start)
        if count >= settings.CODE_DAILY_SEND_LIMIT:
            return False, "Daily verification code limit reached"

        latest = await repo.email_code_latest_for_email(email, purpose)
        if latest and latest.locked_until and now() < latest.locked_until:
            return False, "Verification code input is temporarily locked"

        code = EmailService.generate_code()
        expires_at = now() + timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES)

        old_codes = await repo.email_code_list_unused_for_email(email, purpose)
        for old_code in old_codes:
            await repo.email_code_delete(old_code)

        verification = EmailVerificationCode(
            email=email,
            code_hash=await hash_password_async(code),
            purpose=purpose,
            expires_at=expires_at,
        )
        repo.email_code_add(verification)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # D-02: enqueue background SMTP send (no synchronous send on request thread).
        pool = get_arq_pool()
        await pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, email, code, purpose)
        log_event(logger, logging.INFO, "verificationCodeQueued", email=email, purpose=purpose)
        return True, "queued"

    @staticmethod
    async def verify_code_or_raise(
        db: AsyncSession,
        email: str,
        code: str,
        purpose: str = "register",
    ) -> None:
        """Verify the code and mark it used; raises on any failure."""
        record = await EmailService.get_valid_code_or_raise(db, email, code, purpose)
        EmailService.mark_code_used(record)
        await db.commit()
        log_event(logger, logging.INFO, "verificationCodeAccepted", email=email, purpose=purpose)

    @staticmethod
    async def get_valid_code_or_raise(
        db: AsyncSession,
        email: str,
        code: str,
        purpose: str = "register",
    ) -> EmailVerificationCode:
        """Return the latest unused code row that matches `code`.

        Raises CodeNotFoundException / CodeExpiredException / InvalidCodeException.
        Locks the latest row FOR UPDATE so concurrent error-count updates serialise.
        """
        email = normalize_email(email)
        record = await UserRepository(db).email_code_latest_unused_for_email(
            email, purpose, for_update=True,
        )
        if not record:
            raise CodeNotFoundException()

        if record.locked_until and now() < record.locked_until:
            raise InvalidCodeException(detail="Verification code input is temporarily locked")
        if now() > record.expires_at:
            raise CodeExpiredException()

        if not await verify_password_async(code, record.code_hash):
            record.error_count = (record.error_count or 0) + 1
            if record.error_count >= settings.MAX_CODE_ERRORS:
                record.locked_until = now() + timedelta(hours=settings.CODE_ERROR_LOCK_HOURS)
                # D-11: preserve inner db.commit() for 1:1 source parity — the
                # error-count + lockout update must persist even when the caller
                # rolls back its own transaction.
                await db.commit()
                raise InvalidCodeException(detail="Too many invalid verification attempts")
            # D-11: preserve inner db.commit() for 1:1 source parity (error-count update).
            await db.commit()
            raise InvalidCodeException()

        return record

    @staticmethod
    def mark_code_used(record: EmailVerificationCode) -> None:
        record.used_at = now()
        record.error_count = 0
