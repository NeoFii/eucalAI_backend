"""
邮件服务模块
提供验证码发送和验证功能
"""

import logging
import random
import smtplib
import ssl
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.password import hash_password, verify_password
from common.utils.timezone import now
from user.config import settings
from user.models.email_verification_code import EmailVerificationCode
from common.core.exceptions import (
    CodeExpiredException,
    CodeNotFoundException,
    InvalidCodeException,
)

logger = logging.getLogger(__name__)


class EmailService:
    """邮件服务类"""

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
        """生成6位随机验证码"""
        return f"{random.randint(0, 999999):06d}"

    def _send_email(self, email: str, code: str, purpose: str) -> Tuple[bool, str]:
        """发送邮件"""
        if not self.smtp_host or not self.smtp_user:
            logger.debug(f"开发环境 - 模拟发送邮件: 邮箱={email}, 验证码={code}, 用途={purpose}")
            print(f"\n{'='*50}")
            print(f"发送邮件到: {email}")
            print(f"验证码: {code}")
            print(f"用途: {purpose}")
            print(f"{'='*50}\n")
            return True, ""

        try:
            logger.info(f"发送邮件: 邮箱={email}, 用途={purpose}")
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)

                if purpose == "register":
                    subject = "【Eucal AI】注册验证码"
                    body = f"""您好！\n\n您的注册验证码是：{code}\n\n验证码有效期为 {self.code_expire_minutes} 分钟，请尽快完成注册。\n\n如果这不是您的操作，请忽略此邮件。\n\n---\nEucal AI 团队\n"""
                elif purpose == "login":
                    subject = "【Eucal AI】登录验证码"
                    body = f"""您好！\n\n您的登录验证码是：{code}\n\n验证码有效期为 {self.code_expire_minutes} 分钟，请尽快完成登录。\n\n如果这不是您的操作，请忽略此邮件。\n\n---\nEucal AI 团队\n"""
                else:
                    subject = "【Eucal AI】密码重置验证码"
                    body = f"""您好！\n\n您正在重置密码，您的验证码是：{code}\n\n验证码有效期为 {self.code_expire_minutes} 分钟，请尽快完成操作。\n\n如果这不是您的操作，请忽略此邮件。\n\n---\nEucal AI 团队\n"""

                message = MIMEMultipart("alternative")
                message["From"] = f"{self.smtp_from} <{self.smtp_user}>"
                message["To"] = email
                message["Subject"] = subject
                message.attach(MIMEText(body, "plain", "utf-8"))
                server.sendmail(self.smtp_user, email, message.as_string())

            return True, ""
        except Exception as e:
            logger.error(f"邮件发送失败: 邮箱={email}, 错误={str(e)}")
            return False, f"邮件发送失败: {str(e)}"

    async def send_verification_code(
        self, db: AsyncSession, email: str, purpose: str = "register"
    ) -> Tuple[bool, str]:
        """发送验证码"""
        # 检查今日发送次数
        today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count()).select_from(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.created_at >= today_start,
            )
        )
        count = result.scalar() or 0
        if count >= 3:
            return False, "今日发送次数已达上限（3次），请明天再试"

        # 检查是否被锁定
        result = await db.execute(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            ).order_by(EmailVerificationCode.created_at.desc()).limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest and latest.locked_until and now() < latest.locked_until:
            return False, "验证码输入错误次数过多，请稍后再试"

        # 生成验证码
        code = self.generate_code()
        expires_at = now() + timedelta(minutes=self.code_expire_minutes)

        # 删除该邮箱该用途下未使用的旧验证码
        result = await db.execute(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            )
        )
        old_codes = result.scalars().all()
        for old_code in old_codes:
            await db.delete(old_code)

        # 创建新验证码记录
        code_hash = hash_password(code)
        verification = EmailVerificationCode(
            email=email,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        db.add(verification)
        await db.commit()

        logger.info(f"验证码已保存至数据库（哈希存储），邮箱: {email}, 用途: {purpose}")
        return self._send_email(email, code, purpose)

    async def verify_code_or_raise(
        self, db: AsyncSession, email: str, code: str, purpose: str = "register"
    ) -> None:
        """验证验证码，验证失败则抛出异常"""
        result = await db.execute(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            ).order_by(EmailVerificationCode.created_at.desc()).limit(1)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise CodeNotFoundException()

        if record.locked_until and now() < record.locked_until:
            raise InvalidCodeException(detail="验证码输入错误次数过多，请稍后再试")

        if now() > record.expires_at:
            raise CodeExpiredException()

        if not verify_password(code, record.code_hash):
            record.error_count = (record.error_count or 0) + 1

            if record.error_count >= self.MAX_CODE_ERRORS:
                record.locked_until = now() + timedelta(hours=self.ERROR_COUNT_EXPIRE_HOURS)
                await db.commit()
                raise InvalidCodeException(detail=f"验证码错误次数过多，请{self.ERROR_COUNT_EXPIRE_HOURS}小时后再试")

            await db.commit()
            raise InvalidCodeException()

        record.used_at = now()
        record.error_count = 0
        await db.commit()
        logger.info(f"验证码验证成功: 邮箱={email}, 用途={purpose}")


email_service = EmailService()
