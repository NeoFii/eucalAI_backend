"""Bootstrap super-admin on startup (idempotent + MySQL named-lock).

Ported from `services/admin-service/src/services/bootstrap_service.py` in
Plan 05-01 / Task 2. The source's flat-package imports (`core.db`,
`core.enums`, `repositories.admin_user_repository`, `utils.password`,
`common.utils.nanoid_uid`, `common.utils.password`, `common.utils.timezone`,
`services.audit_service`) are rewritten to their api_service namespace
equivalents (see the imports below). Note: the source's `core.enums` lives
on `api_service.models.enums` in api-service — there is no api_service
`core.enums` module.

Constants `LOCK_NAME` (`"bootstrap_super_admin"`) and `LOCK_TIMEOUT_SECONDS`
(10) are preserved verbatim. The MySQL named lock prevents multiple workers
from racing to create the super admin during startup.

Per Plan 05-01 Task 2 / Pitfall 6, this service is registered with
`main.py` at lifespan priority=25 (after DB at 20, before Redis at 30).
"""

from __future__ import annotations

import logging

from api_service.common.security.password import hash_password_async
from api_service.common.utils.nanoid_uid import generate_nanoid_uid
from api_service.common.utils.password_policy import check_password_strength
from api_service.common.utils.timezone import now
from api_service.core.config import settings
from api_service.core.db import get_db_context
from api_service.models import AdminUser
from api_service.models.enums import AdminRole, AdminStatus
from api_service.repositories.admin_user_repository import AdminUserRepository
from api_service.services.admin.audit_service import AdminAuditService

logger = logging.getLogger(__name__)


class AdminBootstrapService:
    """Initialize the first super admin when needed."""

    LOCK_NAME = "bootstrap_super_admin"
    LOCK_TIMEOUT_SECONDS = 10

    @classmethod
    async def ensure_super_admin(cls) -> bool:
        """Create or update the bootstrap super admin.

        Returns True iff a new super admin row was inserted on this call;
        False otherwise (idempotent reentry).
        """
        async with get_db_context() as db:
            active_count = await cls._count_active_super_admins(db)
            if active_count > 0:
                await cls._maybe_update_existing_super_admin(db)
                return False

            if not settings.BOOTSTRAP_SUPERADMIN_ENABLED:
                if settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP:
                    raise RuntimeError(
                        "No active super_admin and bootstrap is disabled"
                    )
                logger.warning("No active super_admin found; bootstrap disabled")
                return False

            cls._validate_bootstrap_settings()

            lock_acquired = await cls._acquire_lock(db)
            if not lock_acquired:
                raise RuntimeError(
                    "Failed to acquire bootstrap lock for super admin initialization"
                )

            try:
                # Double-check under lock to avoid double-create with concurrent workers.
                active_count = await cls._count_active_super_admins(db)
                if active_count > 0:
                    await cls._maybe_update_existing_super_admin(db)
                    return False

                admin, created = await cls._upsert_bootstrap_super_admin(db)
                await cls._record_bootstrap_audit(db, admin, created)
                await db.commit()
                return created
            finally:
                await cls._release_lock(db)

    @classmethod
    async def _count_active_super_admins(cls, db) -> int:
        return await AdminUserRepository(db).count_active_super_admins()

    @classmethod
    async def _maybe_update_existing_super_admin(cls, db) -> bool:
        if not settings.BOOTSTRAP_SUPERADMIN_EMAIL:
            return False
        if not (
            settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS
            or settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS
        ):
            return False

        admin = await AdminUserRepository(db).get_active_super_admin_by_email(
            settings.BOOTSTRAP_SUPERADMIN_EMAIL
        )
        if admin is None:
            return False

        changed = False
        if (
            settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS
            and settings.BOOTSTRAP_SUPERADMIN_NAME
        ):
            if admin.name != settings.BOOTSTRAP_SUPERADMIN_NAME:
                admin.name = settings.BOOTSTRAP_SUPERADMIN_NAME
                changed = True
        if (
            settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS
            and settings.BOOTSTRAP_SUPERADMIN_PASSWORD
        ):
            ok, message = check_password_strength(settings.BOOTSTRAP_SUPERADMIN_PASSWORD)
            if not ok:
                raise RuntimeError(f"Invalid bootstrap password: {message}")
            admin.password_hash = await hash_password_async(
                settings.BOOTSTRAP_SUPERADMIN_PASSWORD
            )
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
            await db.commit()
        return changed

    @classmethod
    async def _upsert_bootstrap_super_admin(cls, db) -> tuple[AdminUser, bool]:
        existing = await AdminUserRepository(db).get_by_email(
            settings.BOOTSTRAP_SUPERADMIN_EMAIL
        )
        if existing is not None:
            if existing.role != AdminRole.SUPER_ADMIN:
                raise RuntimeError(
                    "Bootstrap email conflicts with a non-super admin account"
                )
            if existing.status != AdminStatus.ACTIVE:
                raise RuntimeError("Bootstrap super_admin exists but is not active")
            if (
                settings.BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS
                and existing.name != settings.BOOTSTRAP_SUPERADMIN_NAME
            ):
                existing.name = settings.BOOTSTRAP_SUPERADMIN_NAME
            if settings.BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS:
                ok, message = check_password_strength(
                    settings.BOOTSTRAP_SUPERADMIN_PASSWORD
                )
                if not ok:
                    raise RuntimeError(f"Invalid bootstrap password: {message}")
                existing.password_hash = await hash_password_async(
                    settings.BOOTSTRAP_SUPERADMIN_PASSWORD
                )
                existing.password_changed_at = now()
                existing.password_changed_by_admin_id = existing.id
            await db.flush()
            return existing, False

        admin = AdminUser(
            uid=generate_nanoid_uid(),
            email=settings.BOOTSTRAP_SUPERADMIN_EMAIL,
            password_hash=await hash_password_async(settings.BOOTSTRAP_SUPERADMIN_PASSWORD),
            name=settings.BOOTSTRAP_SUPERADMIN_NAME,
            role=AdminRole.SUPER_ADMIN,
            is_root=True,
            status=AdminStatus.ACTIVE,
            password_changed_at=now(),
        )
        db.add(admin)
        await db.flush()
        admin.password_changed_by_admin_id = admin.id
        await db.flush()
        return admin, True

    @classmethod
    async def _record_bootstrap_audit(
        cls, db, admin: AdminUser, created: bool
    ) -> None:
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
            reason=(
                "bootstrap create super admin"
                if created
                else "bootstrap reused existing super admin"
            ),
        )

    @classmethod
    async def _acquire_lock(cls, db) -> bool:
        return await AdminUserRepository(db).acquire_named_lock(
            cls.LOCK_NAME,
            cls.LOCK_TIMEOUT_SECONDS,
        )

    @classmethod
    async def _release_lock(cls, db) -> None:
        try:
            await AdminUserRepository(db).release_named_lock(cls.LOCK_NAME)
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


__all__ = ["AdminBootstrapService"]
