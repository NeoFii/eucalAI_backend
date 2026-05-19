"""
认证服务层（api-service 用户域）
处理用户注册、登录、登出等核心业务逻辑

Divergences from user-service source:
- D-09: drop the system-settings gateway, always use `settings.DEFAULT_USER_RPM`.
- All SessionRepository(db) calls rewritten to UserRepository(db).get_session_* / list_active_sessions_for_user / revoke_session / add_session (Phase 3 merge).
- email_service module instance → EmailService class (Pitfall 4).
- Imports moved to api_service.* paths (Pitfall 2).
"""

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
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
from api_service.common.observability import log_event
from api_service.common.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
)
from api_service.common.security.password import (
    hash_password,
    hash_password_async,
    verify_password_async,
)
from api_service.common.utils.email import normalize_email
from api_service.common.utils.nanoid_uid import generate_nanoid_uid
from api_service.common.utils.password_policy import check_password_strength
from api_service.common.utils.snowflake import generate_snowflake_id
from api_service.common.utils.timezone import now
from api_service.core.config import settings
from api_service.models import User, UserSession
from api_service.repositories.user_repository import UserRepository
from api_service.schemas.auth import RegisterRequest
from api_service.services.email_service import EmailService

logger = logging.getLogger(__name__)

MAX_ACTIVE_SESSIONS = 10

_DUMMY_HASH: str | None = None


def _get_dummy_hash() -> str:
    """Constant-time timing equalizer to prevent email-enumeration on /auth/login."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-timing-equalizer")
    return _DUMMY_HASH


class AuthService:
    """认证服务类"""

    @staticmethod
    async def register(db: AsyncSession, data: RegisterRequest) -> User:
        """用户注册"""
        email = normalize_email(data.email)
        user_repo = UserRepository(db)

        # 检查邮箱是否已存在
        if await user_repo.get_by_email(email):
            raise EmailAlreadyExistsException()

        # 检查密码强度
        ok, msg = check_password_strength(data.password, lang=data.lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        # 验证邮箱验证码，但延迟到本地事务成功后再消费
        code_record = await EmailService.get_valid_code_or_raise(
            db, email, data.verification_code, "register"
        )

        # 生成 NanoID UID
        uid = generate_nanoid_uid()

        password_hash = await hash_password_async(data.password)

        # D-09: Phase 4 always reads DEFAULT_USER_RPM constant; admin DB read
        # deferred to Phase 5. The legacy system-settings gateway is intentionally
        # NOT imported here — Phase 4 has no cross-service HTTP for this read.
        # TODO(phase-5): re-introduce dynamic DB read when admin domain ships
        snapshot_rpm = settings.DEFAULT_USER_RPM

        user = User(
            uid=uid,
            email=email,
            password_hash=password_hash,
            status=1,
            email_verified_at=now(),
            rpm_limit=snapshot_rpm,
        )

        user_repo.add(user)
        EmailService.mark_code_used(code_record)
        await db.commit()
        await db.refresh(user)

        log_event(logger, logging.INFO, "userRegisterSuccess", uid=user.uid)
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
        log_event(logger, logging.INFO, "userLoginAttempt", email=email)
        email = normalize_email(email)
        user_repo = UserRepository(db)
        user = await user_repo.get_by_email(email)

        if not user:
            # Equalize timing against the existing-user path to prevent enumeration.
            await verify_password_async("", _get_dummy_hash())
            raise InvalidCredentialsException()

        if user.is_login_locked:
            raise InvalidCredentialsException(
                detail=f"登录失败次数过多，账户已被锁定，请{int((user.login_locked_until - now()).total_seconds() / 60)}分钟后再试"
            )

        if not await verify_password_async(password, user.password_hash):
            user.login_fail_count = (user.login_fail_count or 0) + 1

            if user.login_fail_count >= settings.LOGIN_MAX_FAILURES:
                user.login_locked_until = now() + timedelta(hours=settings.LOGIN_LOCK_DURATION_HOURS)
                log_event(logger, logging.WARNING, "userLoginLocked", uid=user.uid)
                await db.commit()
                raise InvalidCredentialsException(
                    detail=f"登录失败次数过多，账户已被锁定，请{int(settings.LOGIN_LOCK_DURATION_HOURS * 60)}分钟后再试"
                )

            await db.commit()
            raise InvalidCredentialsException()

        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        user.login_fail_count = 0
        user.login_locked_until = None

        # NOTE: We deliberately do NOT revoke other active sessions on a normal
        # login. Allowing the same account to stay signed in on multiple
        # devices/browsers matches mainstream SaaS UX. Sensitive operations
        # (change_password / reset_password) still call _revoke_all_user_sessions.
        access_token, refresh_token = await AuthService._create_session_and_tokens(
            db, user, user_agent, ip_address
        )
        await db.commit()

        log_event(logger, logging.INFO, "userLoginSuccess", uid=user.uid)
        return user, access_token, refresh_token

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        """用户登出"""
        token_jti = get_token_jti(refresh_token)
        user_repo = UserRepository(db)
        session = await user_repo.get_session_by_token_jti(token_jti)

        if not session:
            raise SessionNotFoundException()

        if not await verify_password_async(refresh_token, session.refresh_token_hash):
            raise SessionNotFoundException()

        if session.is_revoked:
            raise SessionNotFoundException()

        user_repo.revoke_session(session)
        await db.commit()
        log_event(logger, logging.INFO, "userLogout")

    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
        """刷新 access_token"""
        payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        if not payload:
            raise InvalidTokenException()

        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="无效的令牌类型")

        token_jti = get_token_jti(refresh_token)
        user_repo = UserRepository(db)
        session = await user_repo.get_session_by_token_jti(token_jti)

        if not session:
            raise SessionNotFoundException()

        if not await verify_password_async(refresh_token, session.refresh_token_hash):
            raise InvalidTokenException()

        if session.is_revoked:
            raise SessionRevokedException()

        if session.is_expired:
            raise SessionExpiredException()

        user = await user_repo.get_by_id(session.user_id)

        if not user or user.status != 1:
            raise UserNotFoundException(detail="用户不存在或已被禁用")

        new_access_token = create_access_token(
            data={"uid": user.uid, "sub": user.uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        new_refresh_token = create_refresh_token(
            data={"uid": user.uid, "sub": user.uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        # Refresh-token rotation: update session in-place (preserve verbatim from source).
        session.token_jti = get_token_jti(new_refresh_token)
        session.refresh_token_hash = await hash_password_async(new_refresh_token)
        session.expires_at = now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await db.commit()

        log_event(logger, logging.INFO, "userTokenRefreshed", uid=user.uid)
        return new_access_token, new_refresh_token

    # Alias the source name so callers from controllers can pick either.
    refresh = refresh_access_token

    @staticmethod
    async def get_current_user(db: AsyncSession, uid: str) -> Optional[User]:
        """通过 uid 获取当前用户"""
        return await UserRepository(db).get_by_uid(uid)

    @staticmethod
    async def verify_email(db: AsyncSession, email: str, code: str) -> User:
        """Verify a user's email and activate the account if needed."""
        email = normalize_email(email)
        code_record = await EmailService.get_valid_code_or_raise(db, email, code, "verify")

        user = await UserRepository(db).get_by_email(email)
        if not user:
            raise UserNotFoundException()
        if user.status == 0:
            raise UserDisabledException()

        if user.status == 2:
            user.status = 1
        user.email_verified_at = now()
        EmailService.mark_code_used(code_record)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str,
        lang: str = "zh",
    ) -> None:
        """修改密码"""
        if not await verify_password_async(old_password, user.password_hash):
            raise InvalidCredentialsException(detail="旧密码错误")

        ok, msg = check_password_strength(new_password, lang=lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        user.password_hash = await hash_password_async(new_password)
        await AuthService.revoke_all_user_sessions(db, user.id)
        await db.commit()
        log_event(logger, logging.INFO, "userPasswordChanged", uid=user.uid)

    @staticmethod
    async def _create_session_and_tokens(
        db: AsyncSession,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[str, str]:
        user_repo = UserRepository(db)
        active_sessions = await user_repo.list_active_sessions_for_user(user.id)
        if len(active_sessions) >= MAX_ACTIVE_SESSIONS:
            oldest = min(active_sessions, key=lambda s: s.created_at)
            user_repo.revoke_session(oldest)

        access_token = create_access_token(
            data={"uid": user.uid, "sub": user.uid},
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
            refresh_token_hash=await hash_password_async(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )
        user_repo.add_session(session)
        user.last_login_at = now()
        user.last_login_ip = ip_address
        return access_token, refresh_token

    @staticmethod
    async def revoke_all_user_sessions(db: AsyncSession, user_id: int) -> None:
        """注销用户的所有会话"""
        user_repo = UserRepository(db)
        sessions = await user_repo.list_active_sessions_for_user(user_id)
        for session in sessions:
            user_repo.revoke_session(session)

    @staticmethod
    async def login_with_code(
        db: AsyncSession,
        email: str,
        code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, str, str]:
        """邮箱验证码登录"""
        email = normalize_email(email)
        code_record = await EmailService.get_valid_code_or_raise(db, email, code, "login")

        user = await UserRepository(db).get_by_email(email)

        if not user:
            raise UserNotFoundException()

        if user.status == 0:
            raise UserDisabledException()
        if user.status == 2:
            raise EmailNotVerifiedException()

        user.login_fail_count = 0
        user.login_locked_until = None

        # See note in `login` — code-based login also keeps prior sessions alive.
        access_token, refresh_token = await AuthService._create_session_and_tokens(
            db, user, user_agent, ip_address
        )
        EmailService.mark_code_used(code_record)
        await db.commit()

        log_event(logger, logging.INFO, "userCodeLoginSuccess", uid=user.uid)
        return user, access_token, refresh_token

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        email: str,
        code: str,
        new_password: str,
        lang: str = "zh",
    ) -> None:
        """通过邮箱验证码重置密码"""
        email = normalize_email(email)
        code_record = await EmailService.get_valid_code_or_raise(
            db, email, code, "reset_password"
        )

        user = await UserRepository(db).get_by_email(email)

        if not user:
            raise UserNotFoundException()
        if user.status == 0:
            raise UserDisabledException()

        ok, msg = check_password_strength(new_password, lang=lang)
        if not ok:
            raise WeakPasswordException(detail=msg)

        user.password_hash = await hash_password_async(new_password)
        EmailService.mark_code_used(code_record)
        await AuthService.revoke_all_user_sessions(db, user.id)
        await db.commit()
        log_event(logger, logging.INFO, "userPasswordReset", uid=user.uid)
