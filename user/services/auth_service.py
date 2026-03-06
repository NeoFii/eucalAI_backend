"""
认证服务层
处理用户注册、登录、登出等核心业务逻辑
"""

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    EmailAlreadyExistsException,
    EmailNotVerifiedException,
    InvalidCredentialsException,
    InvalidTokenException,
    SessionExpiredException,
    SessionNotFoundException,
    SessionRevokedException,
    TokenExpiredException,
    UserDisabledException,
    UserNotFoundException,
    WeakPasswordException,
)
from common.utils import (
    create_access_token,
    create_refresh_token,
    generate_snowflake_id,
    hash_password,
    verify_password,
)
from common.utils.jwt import decode_token, get_token_jti
from common.utils.timezone import now
from user.config import settings
from user.models import User, UserSession
from user.schemas import RegisterRequest
from user.services.email_service import email_service
from user.utils.admin_client import verify_and_use_invitation_code

logger = logging.getLogger(__name__)

LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_DURATION_HOURS = 1


class AuthService:
    """认证服务类"""

    @staticmethod
    async def register(db: AsyncSession, data: RegisterRequest) -> User:
        """
        用户注册

        通过内部 API 调用管理服务验证并核销邀请码
        """
        # 检查邮箱是否已存在
        result = await db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise EmailAlreadyExistsException()

        # 检查密码强度
        from user.utils.password import check_password_strength
        ok, msg = check_password_strength(data.password, lang=data.lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        # 验证邮箱验证码
        await email_service.verify_code_or_raise(db, data.email, data.verification_code, "register")

        # 生成雪花 ID 作为 uid
        uid = generate_snowflake_id()

        # 通过内部 API 验证并核销邀请码
        await verify_and_use_invitation_code(data.invitation_code, uid)

        # 哈希密码
        password_hash = hash_password(data.password)

        # 创建用户
        user = User(
            uid=uid,
            email=data.email,
            password_hash=password_hash,
            status=1,
            email_verified_at=now(),
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"用户注册成功: {user.email}")
        return user

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, str, str]:
        """用户登录"""
        logger.info(f"尝试登录: {email}")
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise InvalidCredentialsException()

        if user.is_login_locked:
            raise InvalidCredentialsException(
                detail=f"登录失败次数过多，账户已被锁定，请{int((user.login_locked_until - now()).total_seconds() / 60)}分钟后再试"
            )

        if not verify_password(password, user.password_hash):
            user.login_fail_count = (user.login_fail_count or 0) + 1

            if user.login_fail_count >= LOGIN_MAX_FAILURES:
                user.login_locked_until = now() + timedelta(hours=LOGIN_LOCK_DURATION_HOURS)
                logger.warning(f"用户 {email} 登录失败次数过多，账户已被锁定")
                await db.commit()
                raise InvalidCredentialsException(
                    detail=f"登录失败次数过多，账户已被锁定，请{int(LOGIN_LOCK_DURATION_HOURS * 60)}分钟后再试"
                )

            await db.commit()
            raise InvalidCredentialsException()

        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        # 登录成功
        user.login_fail_count = 0
        user.login_locked_until = None

        await AuthService._revoke_all_user_sessions(db, user.id)

        access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        refresh_token = create_refresh_token(
            data={"uid": user.uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        session_id = generate_snowflake_id()
        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            token_jti=get_token_jti(refresh_token),
            refresh_token_hash=hash_password(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(session)
        user.last_login_at = now()
        user.last_login_ip = ip_address
        await db.commit()

        logger.info(f"用户登录成功: {email}, IP: {ip_address}")
        return user, access_token, refresh_token

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        """用户登出"""
        token_jti = get_token_jti(refresh_token)
        result = await db.execute(select(UserSession).where(UserSession.token_jti == token_jti))
        session = result.scalar_one_or_none()

        if not session:
            raise SessionNotFoundException()

        if not verify_password(refresh_token, session.refresh_token_hash):
            raise SessionNotFoundException()

        if session.is_revoked:
            raise SessionNotFoundException()

        session.revoked_at = now()
        await db.commit()
        logger.info("用户登出成功")

    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
        """刷新 access_token"""
        payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        if not payload:
            raise InvalidTokenException()

        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="无效的令牌类型")

        token_jti = get_token_jti(refresh_token)
        result = await db.execute(select(UserSession).where(UserSession.token_jti == token_jti))
        session = result.scalar_one_or_none()

        if not session:
            raise SessionNotFoundException()

        if not verify_password(refresh_token, session.refresh_token_hash):
            raise InvalidTokenException()

        if session.is_revoked:
            raise SessionRevokedException()

        if session.is_expired:
            raise SessionExpiredException()

        user_result = await db.execute(select(User).where(User.id == session.user_id))
        user = user_result.scalar_one_or_none()

        if not user or user.status != 1:
            raise UserNotFoundException(detail="用户不存在或已被禁用")

        new_access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        new_refresh_token = create_refresh_token(
            data={"uid": user.uid, "sub": str(user.uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        logger.info(f"刷新 access_token 成功: uid={user.uid}")
        return new_access_token, new_refresh_token

    @staticmethod
    async def get_current_user(db: AsyncSession, uid: int) -> Optional[User]:
        """通过 uid 获取当前用户"""
        result = await db.execute(select(User).where(User.uid == uid))
        return result.scalar_one_or_none()

    @staticmethod
    async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str, lang: str = "zh") -> None:
        """修改密码"""
        if not verify_password(old_password, user.password_hash):
            raise InvalidCredentialsException(detail="旧密码错误")

        from user.utils.password import check_password_strength
        ok, msg = check_password_strength(new_password, lang=lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        user.password_hash = hash_password(new_password)
        await db.commit()
        await AuthService._revoke_all_user_sessions(db, user.id)
        logger.info(f"用户修改密码成功: uid={user.uid}")

    @staticmethod
    async def _revoke_all_user_sessions(db: AsyncSession, user_id: int) -> None:
        """注销用户的所有会话"""
        result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.revoked_at = now()
        await db.commit()

    @staticmethod
    async def login_with_code(
        db: AsyncSession,
        email: str,
        code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, str, str]:
        """邮箱验证码登录"""
        await email_service.verify_code_or_raise(db, email, code, "login")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundException()

        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        await AuthService._revoke_all_user_sessions(db, user.id)

        access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        refresh_token = create_refresh_token(
            data={"uid": user.uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        session_id = generate_snowflake_id()
        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            token_jti=get_token_jti(refresh_token),
            refresh_token_hash=hash_password(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(session)
        user.last_login_at = now()
        user.last_login_ip = ip_address
        await db.commit()

        logger.info(f"用户验证码登录成功: {email}, IP: {ip_address}")
        return user, access_token, refresh_token

    @staticmethod
    async def reset_password(db: AsyncSession, email: str, code: str, new_password: str, lang: str = "zh") -> None:
        """通过邮箱验证码重置密码"""
        await email_service.verify_code_or_raise(db, email, code, "reset_password")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundException()

        from user.utils.password import check_password_strength
        ok, msg = check_password_strength(new_password, lang=lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        user.password_hash = hash_password(new_password)
        await db.commit()
        await AuthService._revoke_all_user_sessions(db, user.id)
        logger.info(f"用户重置密码成功: {email}")
