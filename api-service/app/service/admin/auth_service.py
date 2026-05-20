"""Admin authentication service.

Ported from `services/admin-service/src/services/auth_service.py` in
Plan 05-01 / Task 2. Import-rewrite policy (Pitfall 11+12): every source
import that uses a flat package prefix is rewritten to the app
namespace -- `common.token_blacklist`, `common.utils.jwt`,
`common.utils.password`, `repositories`, `services.audit_service`,
`common.observability`, `common.utils.timezone`, `common.core.exceptions`,
`core.config`, and the `utils.password.check_password_strength` helper all
land under their new app paths (see the matching imports below).

D-02b semantics preserved: every `await AdminAuditService.record(...)` is
followed by `await db.commit()`. No legacy audit-commit wrapper is used
(Pitfall 2, Pitfall 13).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import (
    AuthenticationException,
    InvalidCredentialsException,
    InvalidTokenException,
    TokenExpiredException,
    WeakPasswordException,
)
from app.common.observability import log_event
from app.common.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
)
from app.common.security.password import (
    hash_password,
    hash_password_async,
    verify_password_async,
)
from app.common.security.token_blacklist import (
    blacklist_token,
    is_token_blacklisted,
)
from app.common.utils.password_policy import check_password_strength
from app.common.utils.timezone import now
from app.core.config import settings
from app.model import AdminUser
from app.repository.admin_user_repository import AdminUserRepository
from app.service.admin.audit_service import AdminAuditService

logger = logging.getLogger(__name__)

LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_DURATION_HOURS = 1

_DUMMY_HASH = hash_password("timing-equalization-dummy")


def _remaining_ttl(token: str) -> int:
    """Seconds until a JWT expires (0 if already expired or unparseable)."""
    payload = decode_token(token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    if not payload or "exp" not in payload:
        return 0
    exp = payload["exp"]
    remaining = int(exp - datetime.now(timezone.utc).timestamp())
    return max(remaining, 0)


class AdminAuthService:
    """Admin authentication and password workflows."""

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[AdminUser, str]:
        """Authenticate an admin and issue an access token."""
        log_event(logger, logging.INFO, "adminLoginAttempt", email=email)
        user_repo = AdminUserRepository(db)
        admin = await user_repo.get_by_email(email)

        if not admin:
            # Constant-time timing equalizer prevents email enumeration.
            await verify_password_async("dummy", _DUMMY_HASH)
            raise InvalidCredentialsException()

        was_locked = bool(admin.login_locked_until and admin.login_locked_until > now())
        lock_expired = bool(admin.login_locked_until and admin.login_locked_until <= now())
        if was_locked:
            remaining_minutes = int((admin.login_locked_until - now()).total_seconds() / 60)
            raise InvalidCredentialsException(
                detail=f"Too many failed login attempts. Try again in {remaining_minutes} minutes."
            )

        if not await verify_password_async(password, admin.password_hash):
            admin.login_fail_count = (admin.login_fail_count or 0) + 1
            await AdminAuditService.record(
                db,
                actor_admin_id=admin.id,
                target_admin_id=admin.id,
                action="admin_login_failed",
                resource_type="admin_user",
                resource_id=str(admin.uid),
                status="failed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if admin.login_fail_count >= LOGIN_MAX_FAILURES:
                admin.login_locked_until = now() + timedelta(hours=LOGIN_LOCK_DURATION_HOURS)
                await AdminAuditService.record(
                    db,
                    actor_admin_id=admin.id,
                    target_admin_id=admin.id,
                    action="admin_login_locked",
                    resource_type="admin_user",
                    resource_id=str(admin.uid),
                    status="success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                await db.commit()
                raise InvalidCredentialsException(
                    detail=f"Too many failed login attempts. Try again in {int(LOGIN_LOCK_DURATION_HOURS * 60)} minutes."
                )

            await db.commit()
            raise InvalidCredentialsException()

        if admin.status == 0:
            raise InvalidCredentialsException()

        admin.login_fail_count = 0
        admin.login_locked_until = None
        admin.last_login_at = now()
        admin.last_login_ip = ip_address

        access_token = create_access_token(
            data={"uid": admin.uid, "sub": admin.uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        await AdminAuditService.record(
            db,
            actor_admin_id=admin.id,
            target_admin_id=admin.id,
            action="admin_login_success",
            resource_type="admin_user",
            resource_id=str(admin.uid),
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if lock_expired:
            await AdminAuditService.record(
                db,
                actor_admin_id=admin.id,
                target_admin_id=admin.id,
                action="admin_login_unlocked",
                resource_type="admin_user",
                resource_id=str(admin.uid),
                status="success",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        await db.commit()
        log_event(logger, logging.INFO, "adminLoginSuccess", email=email)
        return admin, access_token

    @staticmethod
    async def logout(
        admin: AdminUser,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Log out an admin and revoke active tokens (blacklist both JTIs)."""
        log_event(logger, logging.INFO, "adminLogout", email=admin.email)
        if access_token:
            remaining = _remaining_ttl(access_token)
            await blacklist_token(get_token_jti(access_token), remaining)
        if refresh_token:
            remaining = _remaining_ttl(refresh_token)
            await blacklist_token(get_token_jti(refresh_token), remaining)

    @staticmethod
    async def refresh_access_token(
        db: AsyncSession, refresh_token: str
    ) -> tuple[str, str]:
        """Issue new access and refresh tokens from a refresh token.

        Rotates BOTH tokens, blacklists the old refresh jti.
        """
        old_jti = get_token_jti(refresh_token)
        if await is_token_blacklisted(old_jti):
            raise InvalidTokenException(detail="Refresh token has been revoked")

        payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        if not payload:
            raise InvalidTokenException()
        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="Invalid token type")

        uid = payload.get("uid")
        if not uid:
            raise InvalidTokenException()

        admin = await AdminUserRepository(db).get_by_uid(uid)
        if not admin or admin.status == 0:
            raise AuthenticationException(detail="Account is disabled or does not exist")

        new_access_token = create_access_token(
            data={"uid": uid, "sub": uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        new_refresh_token = create_refresh_token(
            data={"uid": uid, "sub": uid},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        remaining = _remaining_ttl(refresh_token)
        if not await blacklist_token(old_jti, remaining):
            raise InvalidTokenException(detail="Token revocation failed, please retry")

        return new_access_token, new_refresh_token

    @staticmethod
    async def get_current_admin(db: AsyncSession, uid: str) -> Optional[AdminUser]:
        """Return the admin identified by public UID."""
        return await AdminUserRepository(db).get_by_uid(uid)

    @staticmethod
    async def change_password(
        db: AsyncSession,
        admin: AdminUser,
        old_password: str,
        new_password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        access_token_str: str | None = None,
        refresh_token_str: str | None = None,
    ) -> None:
        """Change the admin password and invalidate active tokens.

        Sequence (D-02b): verify → strength-check → set hash → audit → commit
        → blacklist BOTH access and refresh JTIs (so the cookies the client
        still holds can no longer be used; client must log in again).
        """
        if not await verify_password_async(old_password, admin.password_hash):
            raise InvalidCredentialsException(detail="Old password is incorrect")

        ok, message = check_password_strength(new_password)
        if not ok:
            raise WeakPasswordException(detail=message)

        admin.password_hash = await hash_password_async(new_password)
        admin.password_changed_at = now()
        await AdminAuditService.record(
            db,
            actor_admin_id=admin.id,
            target_admin_id=admin.id,
            action="admin_change_password",
            resource_type="admin_user",
            resource_id=str(admin.uid),
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()

        for label, tok in (("access", access_token_str), ("refresh", refresh_token_str)):
            if tok:
                remaining = _remaining_ttl(tok)
                if not await blacklist_token(get_token_jti(tok), remaining):
                    logger.critical(
                        "Failed to revoke %s token after password change: uid=%s",
                        label,
                        admin.uid,
                    )

        log_event(logger, logging.INFO, "adminPasswordChanged", uid=admin.uid)


__all__ = ["AdminAuthService", "LOGIN_LOCK_DURATION_HOURS", "LOGIN_MAX_FAILURES"]
