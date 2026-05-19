"""Admin audit service — write/query audit_log rows, manage action labels.

Ported from `services/admin-service/src/services/audit_service.py` in
Plan 05-01 / Task 2. The source's flat-package imports (`models`,
`models.audit_action_definition`, `repositories`, `schemas.audit_log`,
`common.request_context`) are rewritten to their api_service namespace
equivalents (see the imports below).

Repository class name: the api-service package has `AuditLogRepository`
(class renamed during Phase 3 from the legacy `AdminAuditLogRepository`).
Both expose the same `.add` / `.list_logs` API.

D-02b / Pitfall 2 enforcement: `record(...)` ends with `await db.flush()`,
NOT `await db.commit()`. The caller (service or controller) commits the
whole transaction. This ties audit-row atomicity to the business mutation:
if the business mutation rolls back, so does the audit row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.models import AdminAuditLog, AuditActionDefinition
from api_service.repositories.admin_user_repository import AdminUserRepository
from api_service.repositories.audit_log_repository import AuditLogRepository
from api_service.schemas.admin.audit_log import AdminAuditCategory

# Module-level cache for action definitions (loaded once, refreshed on demand).
# Mirrors the source pattern verbatim.
_action_defs_cache: dict[str, AuditActionDefinition] | None = None
_category_actions_cache: dict[str, tuple[str, ...]] | None = None
_action_labels_cache: dict[str, str] | None = None


class AdminAuditService:
    """Write and query admin audit log records."""

    @staticmethod
    async def _ensure_cache(db: AsyncSession) -> None:
        global _action_defs_cache, _category_actions_cache, _action_labels_cache
        if _action_defs_cache is not None:
            return
        result = await db.execute(
            select(AuditActionDefinition).where(AuditActionDefinition.is_active == True)  # noqa: E712
        )
        defs = result.scalars().all()
        _action_defs_cache = {d.code: d for d in defs}
        _action_labels_cache = {d.code: d.label for d in defs}
        cat_map: dict[str, list[str]] = {}
        for d in defs:
            cat_map.setdefault(d.category, []).append(d.code)
        _category_actions_cache = {k: tuple(v) for k, v in cat_map.items()}

    @staticmethod
    async def refresh_cache(db: AsyncSession) -> None:
        """Force reload action definitions from DB."""
        global _action_defs_cache
        _action_defs_cache = None
        await AdminAuditService._ensure_cache(db)

    @staticmethod
    async def get_category_actions(db: AsyncSession) -> dict[str, tuple[str, ...]]:
        await AdminAuditService._ensure_cache(db)
        return _category_actions_cache or {}

    @staticmethod
    async def get_action_labels(db: AsyncSession) -> dict[str, str]:
        await AdminAuditService._ensure_cache(db)
        return _action_labels_cache or {}

    @staticmethod
    async def get_meta(
        db: AsyncSession,
    ) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
        """Return (categories, action_labels, category_actions) for the /meta endpoint."""
        await AdminAuditService._ensure_cache(db)
        categories = list((_category_actions_cache or {}).keys())
        labels = _action_labels_cache or {}
        category_actions = {k: list(v) for k, v in (_category_actions_cache or {}).items()}
        return categories, labels, category_actions

    @staticmethod
    async def update_action_label(
        db: AsyncSession, code: str, label: str
    ) -> AuditActionDefinition | None:
        """Update the display label for an action code."""
        result = await db.execute(
            select(AuditActionDefinition).where(AuditActionDefinition.code == code)
        )
        action_def = result.scalar_one_or_none()
        if action_def is None:
            return None
        action_def.label = label
        await db.flush()
        global _action_defs_cache
        _action_defs_cache = None
        return action_def

    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        actor_admin_id: int | None,
        target_admin_id: int | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        status: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditLog:
        """Insert an audit log row.

        D-02b / Pitfall 2: this method flushes the row but does NOT commit.
        The caller commits the whole transaction so the audit row shares
        atomicity with the business mutation.
        """
        audit_log = AdminAuditLog(
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        repo = AuditLogRepository(db)
        repo.add(audit_log)
        await db.flush()
        return audit_log

    @staticmethod
    async def record_auto(
        db: AsyncSession,
        *,
        actor_admin_id: int | None,
        target_admin_id: int | None = None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        status: str = "success",
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditLog:
        """Variant of `record` that resolves ip/ua from request context vars."""
        from api_service.common.http.request_context import (
            get_request_ip,
            get_request_user_agent,
        )

        return await AdminAuditService.record(
            db,
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            ip_address=ip_address or get_request_ip(),
            user_agent=user_agent or get_request_user_agent(),
        )

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        category: AdminAuditCategory = "all",
        action: str | None = None,
        actor_uid: str | None = None,
        target_uid: str | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        actor_admin_id = None
        if actor_uid is not None:
            actor_admin_id = await AdminUserRepository(db).get_id_by_uid(actor_uid)
            if actor_admin_id is None:
                return [], 0

        target_admin_id = None
        if target_uid is not None:
            target_admin_id = await AdminUserRepository(db).get_id_by_uid(target_uid)
            if target_admin_id is None:
                return [], 0

        category_actions = None
        if category != "all":
            cat_map = await AdminAuditService.get_category_actions(db)
            category_actions = cat_map.get(category)

        return await AuditLogRepository(db).list_logs(
            page=page,
            page_size=page_size,
            actions=category_actions,
            action=action,
            actor_admin_id=actor_admin_id,
            target_admin_id=target_admin_id,
        )


__all__ = ["AdminAuditService"]
