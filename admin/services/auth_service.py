"""
管理员认证服务
处理管理员登录、登出等核心业务逻辑
"""

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    InvalidCredentialsException,
    InvalidTokenException,
    TokenExpiredException,
)
from common.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from common.utils.jwt import decode_token
from common.utils.timezone import now
from admin.config import settings
from admin.models import AdminUser

logger = logging.getLogger(__name__)

LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_DURATION_HOURS = 1


class AdminAuthService:
    """管理员认证服务类"""

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[AdminUser, str]:
        """管理员登录"""
        logger.info(f"管理员尝试登录: {email}")
        result = await db.execute(select(AdminUser).where(AdminUser.email == email))
        admin = result.scalar_one_or_none()

        if not admin:
            raise InvalidCredentialsException()

        if admin.is_login_locked:
            raise InvalidCredentialsException(
                detail=f"登录失败次数过多，账户已被锁定，请{int((admin.login_locked_until - now()).total_seconds() / 60)}分钟后再试"
            )

        if not verify_password(password, admin.password_hash):
            admin.login_fail_count = (admin.login_fail_count or 0) + 1

            if admin.login_fail_count >= LOGIN_MAX_FAILURES:
                admin.login_locked_until = now() + timedelta(hours=LOGIN_LOCK_DURATION_HOURS)
                logger.warning(f"管理员 {email} 登录失败次数过多，账户已被锁定")
                await db.commit()
                raise InvalidCredentialsException(
                    detail=f"登录失败次数过多，账户已被锁定，请{int(LOGIN_LOCK_DURATION_HOURS * 60)}分钟后再试"
                )

            await db.commit()
            raise InvalidCredentialsException()

        if admin.status == 0:
            raise InvalidCredentialsException(detail="账户已被禁用")

        # 登录成功
        admin.login_fail_count = 0
        admin.login_locked_until = None

        access_token = create_access_token(
            data={"uid": admin.uid, "sub": str(admin.uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        admin.last_login_at = now()
        admin.last_login_ip = ip_address
        await db.commit()

        logger.info(f"管理员登录成功: {email}, IP: {ip_address}")
        return admin, access_token

    @staticmethod
    async def logout(admin: AdminUser) -> None:
        """管理员登出"""
        logger.info(f"管理员登出: {admin.email}")
        # 管理员使用简单的 Token 机制，不需要会话管理

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> str:
        """刷新 access_token"""
        payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        if not payload:
            raise InvalidTokenException()

        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="无效的令牌类型")

        uid = payload.get("uid")
        if not uid:
            raise InvalidTokenException()

        new_access_token = create_access_token(
            data={"uid": uid, "sub": str(uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        logger.info(f"刷新 access_token 成功: uid={uid}")
        return new_access_token

    @staticmethod
    async def get_current_admin(db: AsyncSession, uid: int) -> Optional[AdminUser]:
        """通过 uid 获取当前管理员"""
        result = await db.execute(select(AdminUser).where(AdminUser.uid == uid))
        return result.scalar_one_or_none()

    @staticmethod
    async def change_password(
        db: AsyncSession, admin: AdminUser, old_password: str, new_password: str
    ) -> None:
        """修改密码"""
        if not verify_password(old_password, admin.password_hash):
            raise InvalidCredentialsException(detail="旧密码错误")

        from admin.utils.password import check_password_strength
        ok, msg = check_password_strength(new_password)
        if not ok:
            from common.core.exceptions import WeakPasswordException
            raise WeakPasswordException(detail=msg)

        admin.password_hash = hash_password(new_password)
        await db.commit()
        logger.info(f"管理员修改密码成功: uid={admin.uid}")
