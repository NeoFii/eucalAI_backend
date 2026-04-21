"""User repository."""

from __future__ import annotations

from sqlalchemy import func, select

from common.db import BaseRepository
from user_service.models import User


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    async def get_by_uid(self, uid: int) -> User | None:
        return (await self.session.execute(select(User).where(User.uid == uid))).scalar_one_or_none()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)

    async def get_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)
