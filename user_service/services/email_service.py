"""Email verification service for user-service."""

from __future__ import annotations

import logging
import random
import smtplib
import ssl
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import CodeExpiredException, CodeNotFoundException, InvalidCodeException
from common.utils.password import hash_password, verify_password
from common.utils.timezone import now
from user_service.config import settings
from user_service.models.email_verification_code import EmailVerificationCode

logger = logging.getLogger(__name__)


class EmailService:
    """Create, send, and verify user email codes."""

    MAX_CODE_ERRORS = 5
    ERROR_COUNT_EXPIRE_HOURS = 24

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_tls = settings.SMTP_TLS
        self.smtp_from = settings.SMTP_FROM
        self.code_expire_minutes = settings.EMAIL_CODE_EXPIRE_MINUTES

    def generate_code(self) -> str:
        return f"{random.randint(0, 999999):06d}"

    def _send_email(self, email: str, code: str, purpose: str) -> tuple[bool, str]:
        if not self.smtp_host or not self.smtp_user:
            logger.debug("Mock email send: email=%s purpose=%s code=%s", email, purpose, code)
            return True, ""

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)

                if purpose == "register":
                    subject = "[Eucal AI] Registration verification code"
                    body = f"Your verification code is {code}. It expires in {self.code_expire_minutes} minutes."
                elif purpose == "login":
                    subject = "[Eucal AI] Login verification code"
                    body = f"Your login code is {code}. It expires in {self.code_expire_minutes} minutes."
                else:
                    subject = "[Eucal AI] Password reset verification code"
                    body = f"Your password reset code is {code}. It expires in {self.code_expire_minutes} minutes."

                message = MIMEMultipart("alternative")
                message["From"] = f"{self.smtp_from} <{self.smtp_user}>"
                message["To"] = email
                message["Subject"] = subject
                message.attach(MIMEText(body, "plain", "utf-8"))
                server.sendmail(self.smtp_user, email, message.as_string())
            return True, ""
        except Exception as exc:
            logger.error("Email send failed: email=%s error=%s", email, exc)
            return False, f"Email send failed: {exc}"

    async def send_verification_code(
        self,
        db: AsyncSession,
        email: str,
        purpose: str = "register",
    ) -> tuple[bool, str]:
        today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        count_stmt = select(func.count()).select_from(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= today_start,
        )
        count = (await db.execute(count_stmt)).scalar() or 0
        if count >= 3:
            return False, "Daily verification code limit reached"

        latest_stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        latest = (await db.execute(latest_stmt)).scalar_one_or_none()
        if latest and latest.locked_until and now() < latest.locked_until:
            return False, "Verification code input is temporarily locked"

        code = self.generate_code()
        expires_at = now() + timedelta(minutes=self.code_expire_minutes)

        old_stmt = select(EmailVerificationCode).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used_at.is_(None),
        )
        old_codes = (await db.execute(old_stmt)).scalars().all()
        for old_code in old_codes:
            await db.delete(old_code)

        verification = EmailVerificationCode(
            email=email,
            code_hash=hash_password(code),
            purpose=purpose,
            expires_at=expires_at,
        )
        db.add(verification)
        await db.flush()

        try:
            result = self._send_email(email, code, purpose)
            await db.commit()
            logger.info("Verification code persisted: email=%s purpose=%s", email, purpose)
            return result
        except Exception:
            await db.rollback()
            raise

    async def verify_code_or_raise(
        self,
        db: AsyncSession,
        email: str,
        code: str,
        purpose: str = "register",
    ) -> None:
        stmt = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        record = (await db.execute(stmt)).scalar_one_or_none()
        if not record:
            raise CodeNotFoundException()

        if record.locked_until and now() < record.locked_until:
            raise InvalidCodeException(detail="Verification code input is temporarily locked")
        if now() > record.expires_at:
            raise CodeExpiredException()

        if not verify_password(code, record.code_hash):
            record.error_count = (record.error_count or 0) + 1
            if record.error_count >= self.MAX_CODE_ERRORS:
                record.locked_until = now() + timedelta(hours=self.ERROR_COUNT_EXPIRE_HOURS)
                await db.commit()
                raise InvalidCodeException(detail="Too many invalid verification attempts")
            await db.commit()
            raise InvalidCodeException()

        record.used_at = now()
        record.error_count = 0
        await db.commit()
        logger.info("Verification code accepted: email=%s purpose=%s", email, purpose)


email_service = EmailService()