"""User session repository."""

from __future__ import annotations

from sqlalchemy import select

from common.db import BaseRepository
from common.utils.timezone import now
from models import UserSession


class SessionRepository(BaseRepository[UserSession]):
    def __init__(self, session) -> None:
        super().__init__(session, UserSession)

    async def get_by_token_jti(self, token_jti: str) -> UserSession | None:
        return (
            await self.session.execute(select(UserSession).where(UserSession.token_jti == token_jti))
        ).scalar_one_or_none()

    async def list_active_for_user(self, user_id: int) -> list[UserSession]:
        result = await self.session.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        return list(result.scalars().all())

    def add(self, session_obj: UserSession) -> None:
        self.session.add(session_obj)

    def revoke(self, session_obj: UserSession) -> None:
        session_obj.revoked_at = now()
