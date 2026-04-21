"""Invitation-code data-access methods."""

from __future__ import annotations

from sqlalchemy import func, select

from admin_service.models import InvitationCode
from common.db import BaseRepository


class InvitationCodeRepository(BaseRepository[InvitationCode]):
    """Repository for invitation codes."""

    def __init__(self, session) -> None:
        super().__init__(session, InvitationCode)

    async def get_by_code(self, code: str, *, for_update: bool = False) -> InvitationCode | None:
        statement = self._base_query().where(InvitationCode.code == code)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, code_id: int) -> InvitationCode | None:
        return await self.find_one(InvitationCode.id == code_id)

    async def list_codes(
        self,
        *,
        page: int,
        page_size: int,
        status: int | None = None,
    ) -> tuple[list[InvitationCode], int]:
        statement = self._base_query()
        if status is not None:
            statement = statement.where(InvitationCode.status == status)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(statement.subquery()))
            ).scalar()
            or 0
        )
        rows = await self.session.execute(
            statement.order_by(InvitationCode.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_stats(self) -> dict[str, int]:
        total = int(
            (await self.session.execute(select(func.count(InvitationCode.id)))).scalar() or 0
        )
        used = int(
            (
                await self.session.execute(
                    select(func.count(InvitationCode.id)).where(InvitationCode.status == 1)
                )
            ).scalar()
            or 0
        )
        valid = int(
            (
                await self.session.execute(
                    select(func.count(InvitationCode.id)).where(InvitationCode.status == 0)
                )
            ).scalar()
            or 0
        )
        return {"total": total, "used": used, "valid": valid}
