"""Email verification service for user-service."""

from __future__ import annotations

import asyncio
import logging
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import CodeExpiredException, CodeNotFoundException, InvalidCodeException
from common.utils.password import hash_password, verify_password
from common.utils.timezone import now
from core.config import settings
from models.email_verification_code import EmailVerificationCode
from repositories.email_code_repository import EmailCodeRepository
from utils.email import normalize_email

logger = logging.getLogger(__name__)


class EmailService:
    """Create, send, and verify user email codes."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_tls = settings.SMTP_TLS
        self.smtp_from = settings.SMTP_FROM
        self.code_expire_minutes = settings.EMAIL_CODE_EXPIRE_MINUTES

    def generate_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _send_email(self, email: str, code: str, purpose: str) -> tuple[bool, str]:
        if not self.smtp_host or not self.smtp_user:
            logger.debug("Mock email send: email=%s purpose=%s", email, purpose)
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
                elif purpose == "verify":
                    subject = "[Eucal AI] Email verification code"
                    body = f"Your email verification code is {code}. It expires in {self.code_expire_minutes} minutes."
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
            return False, "邮件发送失败，请稍后重试"

    async def send_verification_code(
        self,
        db: AsyncSession,
        email: str,
        purpose: str = "register",
    ) -> tuple[bool, str]:
        email = normalize_email(email)
        repo = EmailCodeRepository(db)
        today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        count = await repo.count_created_since(email, purpose, today_start)
        if count >= settings.CODE_DAILY_SEND_LIMIT:
            return False, "Daily verification code limit reached"

        latest = await repo.latest_for_email(email, purpose)
        if latest and latest.locked_until and now() < latest.locked_until:
            return False, "Verification code input is temporarily locked"

        code = self.generate_code()
        expires_at = now() + timedelta(minutes=self.code_expire_minutes)

        old_codes = await repo.list_unused_for_email(email, purpose)
        for old_code in old_codes:
            await repo.delete(old_code)

        verification = EmailVerificationCode(
            email=email,
            code_hash=hash_password(code),
            purpose=purpose,
            expires_at=expires_at,
        )
        repo.add(verification)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        result = await asyncio.to_thread(self._send_email, email, code, purpose)
        if not result[0]:
            await repo.delete(verification)
            await db.commit()
            return result

        logger.info("Verification code sent: email=%s purpose=%s", email, purpose)
        return result

    async def verify_code_or_raise(
        self,
        db: AsyncSession,
        email: str,
        code: str,
        purpose: str = "register",
    ) -> None:
        record = await self.get_valid_code_or_raise(db, email, code, purpose)
        self.mark_code_used(record)
        await db.commit()
        logger.info("Verification code accepted: email=%s purpose=%s", email, purpose)

    async def get_valid_code_or_raise(
        self,
        db: AsyncSession,
        email: str,
        code: str,
        purpose: str = "register",
    ) -> EmailVerificationCode:
        email = normalize_email(email)
        record = await EmailCodeRepository(db).latest_unused_for_email(
            email, purpose, for_update=True,
        )
        if not record:
            raise CodeNotFoundException()

        if record.locked_until and now() < record.locked_until:
            raise InvalidCodeException(detail="Verification code input is temporarily locked")
        if now() > record.expires_at:
            raise CodeExpiredException()

        if not verify_password(code, record.code_hash):
            record.error_count = (record.error_count or 0) + 1
            if record.error_count >= settings.MAX_CODE_ERRORS:
                record.locked_until = now() + timedelta(hours=settings.CODE_ERROR_LOCK_HOURS)
                await db.commit()
                raise InvalidCodeException(detail="Too many invalid verification attempts")
            await db.commit()
            raise InvalidCodeException()

        return record

    def mark_code_used(self, record: EmailVerificationCode) -> None:
        record.used_at = now()
        record.error_count = 0


email_service = EmailService()
