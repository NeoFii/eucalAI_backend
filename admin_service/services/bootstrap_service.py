"""Bootstrap super admin on startup."""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text

from admin_service.config import settings
from admin_service.models import AdminUser
from admin_service.services.audit_service import AdminAuditService
from admin_service.utils.password import check_password_strength
from admin_service.db import get_db_context
from common.utils import generate_snowflake_id, hash_password
from common.utils.timezone import now

logger = logging.getLogger(__name__)


class AdminBootstrapService:
    """Initialize the first super admin when needed."""

    LOCK_NAME = "bootstrap_super_admin"
    LOCK_TIMEOUT_SECONDS = 10

    @classmethod
    async def ensure_super_admin(cls) -> bool:
        async with get_db_context() as db:
            active_count = await cls._count_active_super_admins(db)
            if active_count > 0:
                await cls._maybe_update_existing_super_admin(db)
                return False

            if not settings.BOOTSTRAP_SUPERADMIN_ENABLED:
                if settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP:
                    raise RuntimeError("No active super_admin and bootstrap is disabled")
                logger.warning("No active super_admin found; bootstrap disabled")
                return False

            cls._validate_bootstrap_settings()

            lock_acquired = await cls._acquire_lock(db)
            if not lock_acquired:
                raise RuntimeError("Failed to acquire bootstrap lock for super admin initialization")

            try:
                active_count = await cls._count_active_super_admins(db)
                if active_count > 0:
                    await cls._maybe_update_existing_super_admin(db)
                    return False

                admin, created = await cls._upsert_bootstrap_super_admin(db)
                await cls._record_bootstrap_audit(db, admin, created)
                return created
            finally:
                await cls._release_lock(db)

    @classmethod
    async def _count_active_super_admins(cls, db) -> int:
        result = await db.execute(
            select(func.count()).select_from(AdminUser).where(
                AdminUser.role == "super_admin",
                AdminUser.status == 1,
            )
        )
        return int(result.scalar() or 0)

    @classmethod
    async def _maybe_update_existing_super_admin(cls, db) -> bool:
        if not settings.BOOTSTRAP_SUPERADMIN_EMAIL:
            return False
        if not (
            settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS
            or settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS
        ):
            return False

        result = await db.execute(
            select(AdminUser).where(
                AdminUser.email == settings.BOOTSTRAP_SUPERADMIN_EMAIL,
                AdminUser.role == "super_admin",
                AdminUser.status == 1,
            )
        )
        admin = result.scalar_one_or_none()
        if admin is None:
            return False

        changed = False
        if settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS and settings.BOOTSTRAP_SUPERADMIN_NAME:
            if admin.name != settings.BOOTSTRAP_SUPERADMIN_NAME:
                admin.name = settings.BOOTSTRAP_SUPERADMIN_NAME
                changed = True
        if settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS and settings.BOOTSTRAP_SUPERADMIN_PASSWORD:
            ok, message = check_password_strength(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
            if not ok:
                raise RuntimeError(f"Invalid bootstrap password: {message}")
            admin.password_hash = hash_password(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
            admin.password_changed_at = now()
            admin.password_changed_by_admin_id = admin.id
            changed = True

        if changed:
            await db.flush()
            await AdminAuditService.record(
                db,
                actor_admin_id=admin.id,
                target_admin_id=admin.id,
                action="bootstrap_super_admin",
                resource_type="admin_user",
                resource_id=str(admin.uid),
                status="success",
                before_data=None,
                after_data={
                    "uid": admin.uid,
                    "email": admin.email,
                    "name": admin.name,
                    "role": admin.role,
                    "status": admin.status,
                },
                reason="bootstrap update existing super admin",
            )
        return changed

    @classmethod
    async def _upsert_bootstrap_super_admin(cls, db) -> tuple[AdminUser, bool]:
        result = await db.execute(
            select(AdminUser).where(AdminUser.email == settings.BOOTSTRAP_SUPERADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.role != "super_admin":
                raise RuntimeError("Bootstrap email conflicts with a non-super admin account")
            if existing.status != 1:
                raise RuntimeError("Bootstrap super_admin exists but is not active")
            if (
                settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS
                and existing.name != settings.BOOTSTRAP_SUPERADMIN_NAME
            ):
                existing.name = settings.BOOTSTRAP_SUPERADMIN_NAME
            if settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS:
                ok, message = check_password_strength(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
                if not ok:
                    raise RuntimeError(f"Invalid bootstrap password: {message}")
                existing.password_hash = hash_password(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
                existing.password_changed_at = now()
                existing.password_changed_by_admin_id = existing.id
            await db.flush()
            return existing, False

        admin = AdminUser(
            uid=generate_snowflake_id(),
            email=settings.BOOTSTRAP_SUPERADMIN_EMAIL,
            password_hash=hash_password(settings.BOOTSTRAP_SUPERADMIN_PASSWORD),
            name=settings.BOOTSTRAP_SUPERADMIN_NAME,
            role="super_admin",
            status=1,
            password_changed_at=now(),
        )
        db.add(admin)
        await db.flush()
        admin.password_changed_by_admin_id = admin.id
        await db.flush()
        return admin, True

    @classmethod
    async def _record_bootstrap_audit(cls, db, admin: AdminUser, created: bool) -> None:
        await AdminAuditService.record(
            db,
            actor_admin_id=admin.id,
            target_admin_id=admin.id,
            action="bootstrap_super_admin",
            resource_type="admin_user",
            resource_id=str(admin.uid),
            status="success",
            before_data=None if created else {"uid": admin.uid},
            after_data={
                "uid": admin.uid,
                "email": admin.email,
                "name": admin.name,
                "role": admin.role,
                "status": admin.status,
            },
            reason="bootstrap create super admin" if created else "bootstrap reused existing super admin",
        )

    @classmethod
    async def _acquire_lock(cls, db) -> bool:
        result = await db.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {"lock_name": cls.LOCK_NAME, "timeout_seconds": cls.LOCK_TIMEOUT_SECONDS},
        )
        return result.scalar() == 1

    @classmethod
    async def _release_lock(cls, db) -> None:
        try:
            await db.execute(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": cls.LOCK_NAME},
            )
        except Exception:
            logger.exception("Failed to release bootstrap lock")

    @classmethod
    def _validate_bootstrap_settings(cls) -> None:
        missing: list[str] = []
        if not settings.BOOTSTRAP_SUPERADMIN_EMAIL:
            missing.append("BOOTSTRAP_SUPERADMIN_EMAIL")
        if not settings.BOOTSTRAP_SUPERADMIN_PASSWORD:
            missing.append("BOOTSTRAP_SUPERADMIN_PASSWORD")
        if not settings.BOOTSTRAP_SUPERADMIN_NAME:
            missing.append("BOOTSTRAP_SUPERADMIN_NAME")
        if missing:
            raise RuntimeError(f"Missing bootstrap settings: {', '.join(missing)}")
        ok, message = check_password_strength(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
        if not ok:
            raise RuntimeError(f"Invalid bootstrap password: {message}")
