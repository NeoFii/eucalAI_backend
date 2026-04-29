"""Admin management service owned by the admin domain."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.exceptions import AdminConflictException, AdminPermissionDeniedException
from admin_service.models import AdminUser
from admin_service.repositories import AdminUserRepository
from admin_service.services.audit_service import AdminAuditService
from admin_service.utils.password import check_password_strength
from common.core.exceptions import NotFoundException, ValidationException
from common.utils.nanoid_uid import generate_nanoid_uid
from common.utils.password import hash_password
from common.utils.timezone import now


class AdminManagementService:
    """Manage admin accounts."""

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
        ip_address: str | None = None,
        user_agent: str | None = None,
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
            password_hash=hash_password(password),
            name=name,
            role="admin",
            status=1,
            created_by_admin_id=actor_admin.id,
            updated_by_admin_id=actor_admin.id,
        )
        user_repo.add(admin)
        await db.flush()
        await db.refresh(admin)

        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=admin.id,
            action="create_admin",
            resource_type="admin_user",
            resource_id=str(admin.uid),
            status="success",
            before_data=None,
            after_data=AdminManagementService.build_admin_snapshot(admin),
            ip_address=ip_address,
            user_agent=user_agent,
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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUser:
        target_admin = await AdminManagementService._get_mutable_target(db, actor_admin, target_uid)
        before_data = AdminManagementService.build_admin_snapshot(target_admin)
        target_admin.status = status
        target_admin.updated_by_admin_id = actor_admin.id
        await db.flush()

        action = "enable_admin" if status == 1 else "disable_admin"
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=target_admin.id,
            action=action,
            resource_type="admin_user",
            resource_id=str(target_admin.uid),
            status="success",
            before_data=before_data,
            after_data=AdminManagementService.build_admin_snapshot(target_admin),
            ip_address=ip_address,
            user_agent=user_agent,
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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUser:
        target_admin = await AdminManagementService._get_mutable_target(db, actor_admin, target_uid)
        ok, message = check_password_strength(new_password)
        if not ok:
            raise ValidationException(message)

        before_data = AdminManagementService.build_admin_snapshot(target_admin)
        target_admin.password_hash = hash_password(new_password)
        target_admin.password_changed_at = now()
        target_admin.password_changed_by_admin_id = actor_admin.id
        target_admin.updated_by_admin_id = actor_admin.id
        await db.flush()

        after_data = AdminManagementService.build_admin_snapshot(target_admin)
        after_data["password_changed_at"] = target_admin.password_changed_at.isoformat()
        await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin.id,
            target_admin_id=target_admin.id,
            action="reset_admin_password",
            resource_type="admin_user",
            resource_id=str(target_admin.uid),
            status="success",
            before_data=before_data,
            after_data=after_data,
            ip_address=ip_address,
            user_agent=user_agent,
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
        target_admin = await AdminManagementService.get_by_uid(db, target_uid)
        if target_admin is None:
            raise NotFoundException("Admin user not found")
        if target_admin.id == actor_admin.id:
            raise AdminPermissionDeniedException("Cannot operate on yourself with this endpoint")
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
            "status": admin.status,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
            "updated_at": admin.updated_at.isoformat() if admin.updated_at else None,
            "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        }
