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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.password import hash_password, verify_password
from common.utils.timezone import now
from user.config import settings
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
        self._table_created = False

    def generate_code(self) -> str:
        """生成6位随机验证码"""
        return f"{random.randint(0, 999999):06d}"

    async def _ensure_table(self, db: AsyncSession) -> None:
        """确保验证码表存在"""
        if self._table_created:
            return

        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS `email_verification_codes` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                `email` VARCHAR(255) NOT NULL COMMENT '邮箱地址',
                `code_hash` VARCHAR(255) NOT NULL COMMENT '验证码哈希',
                `purpose` VARCHAR(20) NOT NULL DEFAULT 'register' COMMENT '用途',
                `expires_at` DATETIME NOT NULL COMMENT '过期时间',
                `used_at` DATETIME NULL COMMENT '使用时间',
                `error_count` INT NOT NULL DEFAULT 0 COMMENT '错误次数',
                `locked_until` DATETIME NULL COMMENT '锁定截止时间',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                PRIMARY KEY (`id`),
                KEY `idx_codes_email` (`email`),
                KEY `idx_codes_email_purpose` (`email`, `purpose`),
                KEY `idx_codes_expires_at` (`expires_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='邮箱验证码表'
        """))
        await db.commit()
        self._table_created = True

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
        await self._ensure_table(db)

        result = await db.execute(
            text("""
                SELECT COUNT(*) as cnt
                FROM email_verification_codes
                WHERE email = :email AND purpose = :purpose AND DATE(created_at) = CURDATE()
            """),
            {"email": email, "purpose": purpose}
        )
        row = result.fetchone()
        if row and row.cnt >= 3:
            return False, "今日发送次数已达上限（3次），请明天再试"

        result = await db.execute(
            text("""
                SELECT locked_until
                FROM email_verification_codes
                WHERE email = :email AND purpose = :purpose
                ORDER BY created_at DESC LIMIT 1
            """),
            {"email": email, "purpose": purpose}
        )
        row = result.fetchone()
        if row and row.locked_until and now() < row.locked_until:
            return False, "验证码输入错误次数过多，请稍后再试"

        code = self.generate_code()
        expires_at = now() + timedelta(minutes=self.code_expire_minutes)

        await db.execute(
            text("DELETE FROM email_verification_codes WHERE email = :email AND purpose = :purpose AND used_at IS NULL"),
            {"email": email, "purpose": purpose}
        )

        code_hash = hash_password(code)

        await db.execute(
            text("""
                INSERT INTO email_verification_codes (email, code_hash, purpose, expires_at, created_at)
                VALUES (:email, :code_hash, :purpose, :expires_at, NOW())
            """),
            {"email": email, "code_hash": code_hash, "purpose": purpose, "expires_at": expires_at}
        )
        await db.commit()

        logger.info(f"验证码已保存至数据库（哈希存储），邮箱: {email}, 用途: {purpose}")
        return self._send_email(email, code, purpose)

    async def verify_code_or_raise(
        self, db: AsyncSession, email: str, code: str, purpose: str = "register"
    ) -> None:
        """验证验证码，验证失败则抛出异常"""
        result = await db.execute(
            text("""
                SELECT id, code_hash, expires_at, error_count, locked_until
                FROM email_verification_codes
                WHERE email = :email AND purpose = :purpose AND used_at IS NULL
                ORDER BY created_at DESC LIMIT 1
            """),
            {"email": email, "purpose": purpose}
        )
        row = result.fetchone()

        if not row:
            raise CodeNotFoundException()

        if row.locked_until and now() < row.locked_until:
            raise InvalidCodeException(detail="验证码输入错误次数过多，请稍后再试")

        if now() > row.expires_at:
            raise CodeExpiredException()

        if not verify_password(code, row.code_hash):
            new_error_count = (row.error_count or 0) + 1

            if new_error_count >= self.MAX_CODE_ERRORS:
                locked_until = now() + timedelta(hours=self.ERROR_COUNT_EXPIRE_HOURS)
                await db.execute(
                    text("""
                        UPDATE email_verification_codes
                        SET error_count = :error_count, locked_until = :locked_until
                        WHERE id = :id
                    """),
                    {"error_count": new_error_count, "locked_until": locked_until, "id": row.id}
                )
                await db.commit()
                raise InvalidCodeException(detail=f"验证码错误次数过多，请{self.ERROR_COUNT_EXPIRE_HOURS}小时后再试")

            await db.execute(
                text("UPDATE email_verification_codes SET error_count = :error_count WHERE id = :id"),
                {"error_count": new_error_count, "id": row.id}
            )
            await db.commit()
            raise InvalidCodeException()

        await db.execute(
            text("UPDATE email_verification_codes SET used_at = NOW(), error_count = 0 WHERE id = :id"),
            {"id": row.id}
        )
        await db.commit()
        logger.info(f"验证码验证成功: 邮箱={email}, 用途={purpose}")


email_service = EmailService()
