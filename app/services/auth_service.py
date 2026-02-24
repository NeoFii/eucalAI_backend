"""
认证服务层
处理用户注册、登录、登出等核心业务逻辑
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    AuthenticationException,
    CodeExpiredException,
    CodeNotFoundException,
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
from app.models import User, UserSession
from app.models.auth_schemas import RegisterRequest
from app.services.email_service import email_service
from app.utils import (
    check_password_strength,
    create_access_token,
    create_refresh_token,
    generate_snowflake_id,
    hash_password,
    verify_password,
)
from app.utils.jwt import decode_token

# 获取日志记录器
logger = logging.getLogger(__name__)

# 登录失败锁定配置
LOGIN_MAX_FAILURES = 5  # 最大失败次数
LOGIN_LOCK_DURATION_HOURS = 1  # 锁定时长（小时）


class AuthService:
    """
    认证服务类
    封装用户认证相关的业务逻辑
    """

    @staticmethod
    async def register(
        db: AsyncSession,
        data: RegisterRequest,
    ) -> User:
        """
        用户注册

        Args:
            db: 数据库会话
            data: 注册请求数据

        Returns:
            User: 创建的用户对象

        Raises:
            EmailAlreadyExistsException: 邮箱已被注册
            WeakPasswordException: 密码强度不足
            CodeNotFoundException: 验证码不存在
            CodeExpiredException: 验证码过期
            InvalidCodeException: 验证码错误
        """
        # 检查邮箱是否已存在
        result = await db.execute(
            select(User).where(User.email == data.email)
        )
        if result.scalar_one_or_none():
            raise EmailAlreadyExistsException()

        # 检查密码强度
        ok, msg = check_password_strength(data.password)
        if not ok:
            raise WeakPasswordException(detail=msg)

        # 验证邮箱验证码（必填）
        await email_service.verify_code_or_raise(
            db, data.email, data.verification_code, "register"
        )

        # 生成雪花 ID 作为 uid
        uid = generate_snowflake_id()

        # 哈希密码
        password_hash = hash_password(data.password)

        # 创建用户（验证码已验证，直接标记为正常状态）
        user = User(
            uid=uid,
            email=data.email,
            password_hash=password_hash,
            status=1,  # 正常状态（验证码已验证）
            email_verified_at=datetime.now(timezone.utc),
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"用户注册成功: {user.email}")
        return user

    @staticmethod
    async def verify_email(
        db: AsyncSession,
        email: str,
        code: str,
    ) -> User:
        """
        验证邮箱

        Args:
            db: 数据库会话
            email: 邮箱地址
            code: 验证码

        Returns:
            User: 验证后的用户对象

        Raises:
            CodeNotFoundException: 验证码不存在
            CodeExpiredException: 验证码过期
            InvalidCodeException: 验证码错误
            UserNotFoundException: 用户不存在
        """
        # 验证验证码
        await email_service.verify_code_or_raise(db, email, code, "register")

        # 查找用户
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundException()

        # 更新用户状态
        user.status = 1
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"邮箱验证成功: {email}")
        return user

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, str, str]:
        """
        用户登录

        Args:
            db: 数据库会话
            email: 登录邮箱
            password: 明文密码
            user_agent: 客户端 User-Agent
            ip_address: 登录 IP

        Returns:
            tuple[User, str, str]: (用户对象, access_token, refresh_token)

        Raises:
            InvalidCredentialsException: 邮箱或密码错误
            UserDisabledException: 账号已被禁用
            EmailNotVerifiedException: 请先验证邮箱
        """
        # 查找用户
        logger.info(f"尝试登录: {email}")
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise InvalidCredentialsException()

        # 检查登录是否被锁定
        if user.is_login_locked:
            raise InvalidCredentialsException(
                detail=f"登录失败次数过多，账户已被锁定，请{int((user.login_locked_until - datetime.now(timezone.utc)).total_seconds() / 60)}分钟后再试"
            )

        # 验证密码
        if not verify_password(password, user.password_hash):
            # 增加登录失败次数
            user.login_fail_count = (user.login_fail_count or 0) + 1

            if user.login_fail_count >= LOGIN_MAX_FAILURES:
                # 锁定账户
                user.login_locked_until = datetime.now(timezone.utc) + timedelta(hours=LOGIN_LOCK_DURATION_HOURS)
                logger.warning(f"用户 {email} 登录失败次数过多，账户已被锁定")
                await db.commit()
                raise InvalidCredentialsException(
                    detail=f"登录失败次数过多，账户已被锁定，请{int(LOGIN_LOCK_DURATION_HOURS * 60)}分钟后再试"
                )

            await db.commit()
            raise InvalidCredentialsException()

        # 检查用户状态
        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        # 登录成功，重置失败次数
        user.login_fail_count = 0
        user.login_locked_until = None

        # 互踢模式：注销用户所有现有会话
        await AuthService._revoke_all_user_sessions(db, user.id)

        # 生成 access_token（JWT，不包含敏感信息）
        access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)}
        )

        # 生成 refresh_token（随机字符串）
        refresh_token = create_refresh_token(
            data={"uid": user.uid}
        )

        # 创建会话记录
        session_id = generate_snowflake_id()
        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_password(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(session)

        # 更新用户最后登录信息
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip_address

        await db.commit()

        logger.info(f"用户登录成功: {email}, IP: {ip_address}")
        return user, access_token, refresh_token

    @staticmethod
    async def logout(
        db: AsyncSession,
        refresh_token: str,
    ) -> None:
        """
        用户登出

        Args:
            db: 数据库会话
            refresh_token: refresh_token

        Raises:
            SessionNotFoundException: 会话不存在
        """
        # 查找并注销会话
        result = await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == refresh_token,
                UserSession.revoked_at.is_(None),
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise SessionNotFoundException()

        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("用户登出成功")

    @staticmethod
    async def refresh_access_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> str:
        """
        刷新 access_token

        Args:
            db: 数据库会话
            refresh_token: refresh_token

        Returns:
            str: 新的 access_token

        Raises:
            InvalidTokenException: 无效的令牌
            TokenExpiredException: 令牌类型错误或已过期
            SessionNotFoundException: 会话不存在
            SessionRevokedException: 会话已注销
            SessionExpiredException: 会话已过期
            UserNotFoundException: 用户不存在或已被禁用
        """
        # 解码 refresh_token
        payload = decode_token(refresh_token)
        if not payload:
            raise InvalidTokenException()

        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="无效的令牌类型")

        # 查找会话
        result = await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == refresh_token,
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise SessionNotFoundException()

        if session.is_revoked:
            raise SessionRevokedException()

        if session.is_expired:
            raise SessionExpiredException()

        # 生成新的 access_token
        user_result = await db.execute(
            select(User).where(User.id == session.user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user or user.status != 1:
            raise UserNotFoundException(detail="用户不存在或已被禁用")

        new_access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)}
        )

        logger.info(f"刷新 access_token 成功: uid={user.uid}")
        return new_access_token

    @staticmethod
    async def get_current_user(
        db: AsyncSession,
        uid: int,
    ) -> Optional[User]:
        """
        通过 uid 获取当前用户

        Args:
            db: 数据库会话
            uid: 用户 uid（雪花 ID）

        Returns:
            Optional[User]: 用户对象
        """
        result = await db.execute(
            select(User).where(User.uid == uid)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str,
    ) -> None:
        """
        修改密码

        Args:
            db: 数据库会话
            user: 用户对象
            old_password: 旧密码
            new_password: 新密码

        Raises:
            InvalidCredentialsException: 旧密码错误
            WeakPasswordException: 新密码强度不足
        """
        # 验证旧密码
        if not verify_password(old_password, user.password_hash):
            raise InvalidCredentialsException(detail="旧密码错误")

        # 检查新密码强度
        ok, msg = check_password_strength(new_password)
        if not ok:
            raise WeakPasswordException(detail=msg)

        # 更新密码
        user.password_hash = hash_password(new_password)
        await db.commit()

        # 修改密码后，注销所有会话（强制重新登录）
        await AuthService._revoke_all_user_sessions(db, user.id)

        logger.info(f"用户修改密码成功: uid={user.uid}")

    @staticmethod
    async def _revoke_all_user_sessions(
        db: AsyncSession,
        user_id: int,
    ) -> None:
        """
        注销用户的所有会话（互踢模式）

        Args:
            db: 数据库会话
            user_id: 用户内部 ID
        """
        result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()

        for session in sessions:
            session.revoked_at = datetime.now(timezone.utc)

        await db.commit()

    @staticmethod
    async def login_with_code(
        db: AsyncSession,
        email: str,
        code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, str, str]:
        """
        邮箱验证码登录

        Args:
            db: 数据库会话
            email: 登录邮箱
            code: 验证码
            user_agent: 客户端 User-Agent
            ip_address: 登录 IP

        Returns:
            tuple[User, str, str]: (用户对象, access_token, refresh_token)

        Raises:
            CodeNotFoundException: 验证码不存在
            CodeExpiredException: 验证码过期
            InvalidCodeException: 验证码错误
            UserNotFoundException: 用户不存在
            UserDisabledException: 账号已被禁用
            EmailNotVerifiedException: 请先验证邮箱
        """
        # 验证验证码
        await email_service.verify_code_or_raise(db, email, code, "login")

        # 查找用户
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundException()

        # 检查用户状态
        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        # 互踢模式：注销用户所有现有会话
        await AuthService._revoke_all_user_sessions(db, user.id)

        # 生成 access_token（JWT，不包含敏感信息）
        access_token = create_access_token(
            data={"uid": user.uid, "sub": str(user.uid)}
        )

        # 生成 refresh_token（随机字符串）
        refresh_token = create_refresh_token(
            data={"uid": user.uid}
        )

        # 创建会话记录
        session_id = generate_snowflake_id()
        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_password(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(session)

        # 更新用户最后登录信息
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip_address

        await db.commit()

        logger.info(f"用户验证码登录成功: {email}, IP: {ip_address}")
        return user, access_token, refresh_token

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        email: str,
        code: str,
        new_password: str,
    ) -> None:
        """
        通过邮箱验证码重置密码

        Args:
            db: 数据库会话
            email: 邮箱地址
            code: 验证码
            new_password: 新密码

        Raises:
            CodeNotFoundException: 验证码不存在
            CodeExpiredException: 验证码过期
            InvalidCodeException: 验证码错误
            UserNotFoundException: 用户不存在
            WeakPasswordException: 新密码强度不足
        """
        # 验证验证码
        await email_service.verify_code_or_raise(db, email, code, "reset_password")

        # 查找用户
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundException()

        # 检查新密码强度
        ok, msg = check_password_strength(new_password)
        if not ok:
            raise WeakPasswordException(detail=msg)

        # 更新密码
        user.password_hash = hash_password(new_password)
        await db.commit()

        # 重置密码后，注销所有会话
        await AuthService._revoke_all_user_sessions(db, user.id)

        logger.info(f"用户重置密码成功: {email}")
