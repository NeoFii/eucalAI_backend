"""Admin account management service (admin-on-admin CRUD).

Ported from `services/admin-service/src/services/management_service.py` in
Plan 05-02 / Task 2, with the **Pitfall 3 rename**:

- File rename: `management_service.py` → `account_service.py`
- Class rename: `AdminManagementService` → `AdminAccountService`
  (avoids collision with Plan 05-03's `AdminEndUserService` which manages
  END users — Phase 5 separates the two namespaces explicitly.)

Standard import rewrites:

- `from core.enums import AdminRole, AdminStatus` →
  `from app.model.enums import AdminRole, AdminStatus`
  (matches the api-service layout — Plan 05-01 made the same fix in
  `bootstrap_service.py` and `core/policies.py`).
- `from core.exceptions import AdminConflictException, AdminPermissionDeniedException` →
  `from app.common.core.exceptions import ...`
- `from repositories import AdminUserRepository` →
  `from app.repository.admin_user_repository import AdminUserRepository`
- `from utils.password import check_password_strength` →
  `from app.common.utils.password_policy import check_password_strength`
- `from common.utils.password import hash_password_async` →
  `from app.common.security.password import hash_password_async`
- `from common.utils.nanoid_uid import generate_nanoid_uid` →
  `from app.common.utils.nanoid_uid import generate_nanoid_uid`
- `from common.utils.timezone import now` →
  `from app.common.utils.timezone import now`
- `from services.audit_service import AdminAuditService` →
  `from app.service.admin.audit_service import AdminAuditService`
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import (
    AdminConflictException,
    AdminPermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from app.common.security.password import hash_password_async
from app.common.utils.nanoid_uid import generate_nanoid_uid
from app.common.utils.password_policy import check_password_strength
from app.common.utils.timezone import now
from app.model import AdminUser
from app.model.enums import AdminRole, AdminStatus
from app.repository.admin_user_repository import AdminUserRepository
from app.service.admin.audit_service import AdminAuditService


class AdminAccountService:
    """Manage admin accounts (admin-on-admin CRUD).

    Renamed from `AdminManagementService` per Pitfall 3 to make the
    distinction with `AdminEndUserService` (Plan 05-03 — end-user CRUD)
    explicit at the import path.
    """

    @staticmethod
    async def list_admins(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AdminUser], int]:
        return await AdminUserRepository(db).list_admins(page=page, page_size=page_size)

    @staticmethod
    async def get_by_uid(db: AsyncSession, uid: str) -> AdminUser | None:
        return await AdminUserRepository(db).get_by_uid(uid)

    @staticmethod
    async def create_admin(
        db: AsyncSession,
        *,
        actor_admin: AdminUser,
        email: str,
        name: str,
        password: str,
        role: int = AdminRole.ADMIN,
    ) -> AdminUser:
        user_repo = AdminUserRepository(db)
        if await user_repo.get_by_email(email):
            raise AdminConflictException("Admin email already exists")

        ok, message = check_password_strength(password)
        if not ok:
            raise ValidationException(message)

        admin = AdminUser(
            uid=generate_nanoid_uid(),
            email=email,
            password_hash=await hash_password_async(password),
            name=name,
            role=role,
            status=AdminStatus.ACTIVE,
            created_by_admin_id=actor_admin.id,
            updated_by_admin_id=actor_admin.id,
        )
        user_repo.add(admin)
        await db.flush()
        await db.refresh(admin)

        await AdminAuditService.record_auto(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=admin.id,
            action="create_admin",
            resource_type="admin_user",
            resource_id=str(admin.uid),
            status="success",
            before_data=None,
            after_data=AdminAccountService.build_admin_snapshot(admin),
        )
        await db.commit()
        await db.refresh(admin)
        return admin

    @staticmethod
    async def update_admin_status(
        db: AsyncSession,
        *,
        actor_admin: AdminUser,
        target_uid: str,
        status: int,
    ) -> AdminUser:
        target_admin = await AdminAccountService._get_mutable_target(
            db, actor_admin, target_uid,
        )
        before_data = AdminAccountService.build_admin_snapshot(target_admin)
        target_admin.status = status
        target_admin.updated_by_admin_id = actor_admin.id
        await db.flush()

        action = "enable_admin" if status == 1 else "disable_admin"
        await AdminAuditService.record_auto(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=target_admin.id,
            action=action,
            resource_type="admin_user",
            resource_id=str(target_admin.uid),
            status="success",
            before_data=before_data,
            after_data=AdminAccountService.build_admin_snapshot(target_admin),
        )
        await db.commit()
        await db.refresh(target_admin)
        return target_admin

    @staticmethod
    async def reset_admin_password(
        db: AsyncSession,
        *,
        actor_admin: AdminUser,
        target_uid: str,
        new_password: str,
    ) -> AdminUser:
        target_admin = await AdminAccountService._get_mutable_target(
            db, actor_admin, target_uid,
        )
        ok, message = check_password_strength(new_password)
        if not ok:
            raise ValidationException(message)

        before_data = AdminAccountService.build_admin_snapshot(target_admin)
        target_admin.password_hash = await hash_password_async(new_password)
        target_admin.password_changed_at = now()
        target_admin.password_changed_by_admin_id = actor_admin.id
        target_admin.updated_by_admin_id = actor_admin.id
        await db.flush()

        after_data = AdminAccountService.build_admin_snapshot(target_admin)
        after_data["password_changed_at"] = target_admin.password_changed_at.isoformat()
        await AdminAuditService.record_auto(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=target_admin.id,
            action="reset_admin_password",
            resource_type="admin_user",
            resource_id=str(target_admin.uid),
            status="success",
            before_data=before_data,
            after_data=after_data,
        )
        await db.commit()
        await db.refresh(target_admin)
        return target_admin

    @staticmethod
    async def update_admin_role(
        db: AsyncSession,
        *,
        actor_admin: AdminUser,
        target_uid: str,
        role: int,
    ) -> AdminUser:
        if not getattr(actor_admin, "is_root", False):
            raise AdminPermissionDeniedException("Only root admin can change roles")

        target_admin = await AdminAccountService.get_by_uid(db, target_uid)
        if target_admin is None:
            raise NotFoundException("Admin user not found")
        if target_admin.id == actor_admin.id:
            raise AdminPermissionDeniedException("Cannot change your own role")
        if getattr(target_admin, "is_root", False):
            raise AdminPermissionDeniedException("Cannot change root admin role")

        before_data = AdminAccountService.build_admin_snapshot(target_admin)
        target_admin.role = role
        target_admin.updated_by_admin_id = actor_admin.id
        await db.flush()

        await AdminAuditService.record_auto(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=target_admin.id,
            action="update_admin_role",
            resource_type="admin_user",
            resource_id=str(target_admin.uid),
            status="success",
            before_data=before_data,
            after_data=AdminAccountService.build_admin_snapshot(target_admin),
        )
        await db.commit()
        await db.refresh(target_admin)
        return target_admin

    @staticmethod
    async def _get_mutable_target(
        db: AsyncSession,
        actor_admin: AdminUser,
        target_uid: str,
    ) -> AdminUser:
        target_admin = await AdminAccountService.get_by_uid(db, target_uid)
        if target_admin is None:
            raise NotFoundException("Admin user not found")
        if target_admin.id == actor_admin.id:
            raise AdminPermissionDeniedException(
                "Cannot operate on yourself with this endpoint"
            )
        if target_admin.is_super_admin:
            raise AdminPermissionDeniedException("Cannot operate on a super admin")
        return target_admin

    @staticmethod
    def build_admin_snapshot(admin: AdminUser) -> dict[str, Any]:
        return {
            "uid": admin.uid,
            "email": admin.email,
            "name": admin.name,
            "role": admin.role,
            "is_root": getattr(admin, "is_root", False),
            "status": admin.status,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
            "updated_at": admin.updated_at.isoformat() if admin.updated_at else None,
            "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        }


__all__ = ["AdminAccountService"]
