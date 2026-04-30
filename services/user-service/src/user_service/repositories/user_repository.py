"""User repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import cast, func, or_, select, Date

from common.db import BaseRepository
from user_service.models import User


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    async def get_by_uid(self, uid: str) -> User | None:
        return (await self.session.execute(select(User).where(User.uid == uid))).scalar_one_or_none()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)

    async def get_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: int | None = None,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        if search:
            search_value = search.strip()
            if search_value:
                escaped = _escape_like(search_value)
                stmt = stmt.where(
                    or_(
                        User.uid == search_value,
                        User.uid.like(f"{escaped}%", escape="\\"),
                        User.email.like(f"%{escaped}%", escape="\\"),
                    )
                )
        if status is not None:
            stmt = stmt.where(User.status == status)
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
        total = int(
            (await self.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
            or 0
        )
        rows = await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total

    def add(self, user: User) -> None:
        self.session.add(user)

    async def get_daily_registrations(
        self, *, start: datetime, end: datetime,
    ) -> list[dict]:
        reg_date = cast(User.created_at, Date).label("reg_date")
        query = (
            select(reg_date, func.count().label("count"))
            .where(User.created_at >= start, User.created_at < end)
            .group_by(reg_date)
            .order_by(reg_date.asc())
        )
        rows = (await self.session.execute(query)).all()
        return [{"date": str(r.reg_date), "count": int(r.count)} for r in rows]

    async def count_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= since)
        )
        return int(result.scalar() or 0)
