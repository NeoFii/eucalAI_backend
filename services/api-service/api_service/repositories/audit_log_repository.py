"""Admin audit-log data-access methods."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from api_service.common.infra.db.repository import BaseRepository
from api_service.models import AdminAuditLog


class AuditLogRepository(BaseRepository[AdminAuditLog]):
    """Repository for admin audit logs."""

    def __init__(self, session) -> None:
        super().__init__(session, AdminAuditLog)

    async def list_logs(
        self,
        *,
        page: int,
        page_size: int,
        actions: tuple[str, ...] | None = None,
        action: str | None = None,
        actor_admin_id: int | None = None,
        target_admin_id: int | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        statement = select(AdminAuditLog).options(
            selectinload(AdminAuditLog.actor_admin),
            selectinload(AdminAuditLog.target_admin),
        )
        count_statement = select(func.count()).select_from(AdminAuditLog)

        if actions is not None:
            statement = statement.where(AdminAuditLog.action.in_(actions))
            count_statement = count_statement.where(AdminAuditLog.action.in_(actions))
        if action:
            statement = statement.where(AdminAuditLog.action == action)
            count_statement = count_statement.where(AdminAuditLog.action == action)
        if actor_admin_id is not None:
            statement = statement.where(AdminAuditLog.actor_admin_id == actor_admin_id)
            count_statement = count_statement.where(AdminAuditLog.actor_admin_id == actor_admin_id)
        if target_admin_id is not None:
            statement = statement.where(AdminAuditLog.target_admin_id == target_admin_id)
            count_statement = count_statement.where(
                AdminAuditLog.target_admin_id == target_admin_id
            )

        statement = statement.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        total = int((await self.session.execute(count_statement)).scalar() or 0)
        rows = await self.session.execute(statement.offset((page - 1) * page_size).limit(page_size))
        return list(rows.scalars().all()), total
