"""Admin user data-access methods."""

from __future__ import annotations

from sqlalchemy import func, select, text

from models import AdminUser
from common.db import BaseRepository


class AdminUserRepository(BaseRepository[AdminUser]):
    """Repository for admin accounts."""

    def __init__(self, session) -> None:
        super().__init__(session, AdminUser)

    async def get_by_email(self, email: str) -> AdminUser | None:
        return await self.find_one(AdminUser.email == email)

    async def get_by_uid(self, uid: str) -> AdminUser | None:
        return await self.find_one(AdminUser.uid == uid)

    async def get_active_super_admin_by_email(self, email: str) -> AdminUser | None:
        return await self.find_one(
            AdminUser.email == email,
            AdminUser.role == "super_admin",
            AdminUser.status == 1,
        )

    async def get_id_by_uid(self, uid: str) -> int | None:
        result = await self.session.execute(select(AdminUser.id).where(AdminUser.uid == uid))
        return result.scalar_one_or_none()

    async def count_active_super_admins(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AdminUser).where(
                AdminUser.role == "super_admin",
                AdminUser.status == 1,
            )
        )
        return int(result.scalar() or 0)

    async def list_admins(self, *, page: int, page_size: int) -> tuple[list[AdminUser], int]:
        statement = select(AdminUser).order_by(AdminUser.created_at.desc(), AdminUser.id.desc())
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(statement.subquery()))
            ).scalar()
            or 0
        )
        rows = await self.session.execute(statement.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total

    async def acquire_named_lock(self, lock_name: str, timeout_seconds: int) -> bool:
        result = await self.session.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {"lock_name": lock_name, "timeout_seconds": timeout_seconds},
        )
        return result.scalar() == 1

    async def release_named_lock(self, lock_name: str) -> None:
        await self.session.execute(
            text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": lock_name},
        )
