"""Data access for user API keys."""

from __future__ import annotations

from sqlalchemy import func, select, update

from api_service.common.infra.db.repository import BaseRepository
from api_service.models import UserApiKey


class ApiKeyRepository(BaseRepository[UserApiKey]):
    """Repository for user-owned API keys."""

    def __init__(self, session) -> None:
        super().__init__(session, UserApiKey)

    def _base_query(self):
        return select(UserApiKey).where(UserApiKey.deleted_at.is_(None))

    async def list_for_user(self, user_id: int) -> list[UserApiKey]:
        result = await self.session.execute(
            self._base_query()
            .where(UserApiKey.user_id == user_id)
            .order_by(UserApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(UserApiKey)
            .where(UserApiKey.deleted_at.is_(None), UserApiKey.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def get_owned_key(
        self,
        key_id: int,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> UserApiKey | None:
        statement = self._base_query().where(
            UserApiKey.id == key_id,
            UserApiKey.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> UserApiKey | None:
        return (
            await self.session.execute(
                self._base_query().where(UserApiKey.key_hash == key_hash)
            )
        ).scalar_one_or_none()

    def add(self, api_key: UserApiKey) -> None:
        self.session.add(api_key)

    async def disable_all_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            update(UserApiKey)
            .where(
                UserApiKey.user_id == user_id,
                UserApiKey.deleted_at.is_(None),
                UserApiKey.status == UserApiKey.STATUS_ACTIVE,
            )
            .values(status=UserApiKey.STATUS_DISABLED)
        )
        return result.rowcount
