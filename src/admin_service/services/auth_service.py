"""Admin authentication service."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.models import AdminUser
from admin_service.repositories import AdminUserRepository
from admin_service.services.audit_service import AdminAuditService
from common.core.exceptions import (
    InvalidCredentialsException,
    InvalidTokenException,
    TokenExpiredException,
    WeakPasswordException,
)
from common.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from common.utils.jwt import decode_token
from common.utils.timezone import now

logger = logging.getLogger(__name__)

LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_DURATION_HOURS = 1


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
        logger.info("Admin login attempt: %s", email)
        user_repo = AdminUserRepository(db)
        admin = await user_repo.get_by_email(email)

        if not admin:
            raise InvalidCredentialsException()

        was_locked = bool(admin.login_locked_until and admin.login_locked_until > now())
        lock_expired = bool(admin.login_locked_until and admin.login_locked_until <= now())
        if was_locked:
            remaining_minutes = int((admin.login_locked_until - now()).total_seconds() / 60)
            raise InvalidCredentialsException(
                detail=f"Too many failed login attempts. Try again in {remaining_minutes} minutes."
            )

        if not verify_password(password, admin.password_hash):
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
            raise InvalidCredentialsException(detail="Account is disabled")

        admin.login_fail_count = 0
        admin.login_locked_until = None
        admin.last_login_at = now()
        admin.last_login_ip = ip_address

        access_token = create_access_token(
            data={"uid": admin.uid, "sub": str(admin.uid)},
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
        logger.info("Admin login succeeded: %s", email)
        return admin, access_token

    @staticmethod
    async def logout(admin: AdminUser) -> None:
        """Log out an admin."""
        logger.info("Admin logout: %s", admin.email)

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> tuple[str, str]:
        """Issue new access and refresh tokens from a refresh token."""
        payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        if not payload:
            raise InvalidTokenException()
        if payload.get("type") != "refresh":
            raise TokenExpiredException(detail="Invalid token type")

        uid = payload.get("uid")
        if not uid:
            raise InvalidTokenException()

        new_access_token = create_access_token(
            data={"uid": uid, "sub": str(uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        new_refresh_token = create_refresh_token(
            data={"uid": uid, "sub": str(uid)},
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )
        return new_access_token, new_refresh_token

    @staticmethod
    async def get_current_admin(db: AsyncSession, uid: int) -> Optional[AdminUser]:
        """Return the admin identified by public UID."""
        return await AdminUserRepository(db).get_by_uid(uid)

    @staticmethod
    async def change_password(
        db: AsyncSession,
        admin: AdminUser,
        old_password: str,
        new_password: str,
    ) -> None:
        """Change the admin password."""
        if not verify_password(old_password, admin.password_hash):
            raise InvalidCredentialsException(detail="Old password is incorrect")

        from admin_service.utils.password import check_password_strength

        ok, message = check_password_strength(new_password)
        if not ok:
            raise WeakPasswordException(detail=message)

        admin.password_hash = hash_password(new_password)
        await db.commit()
        logger.info("Admin password changed: uid=%s", admin.uid)
