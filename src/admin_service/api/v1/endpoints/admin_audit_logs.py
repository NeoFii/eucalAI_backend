"""Admin audit log endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session, require_super_admin
from admin_service.management_schemas import (
    AdminAuditActor,
    AdminAuditCategory,
    AdminAuditLogItem,
    AdminAuditLogListData,
    AdminAuditLogListResponse,
)
from admin_service.models import AdminAuditLog, AdminUser
from admin_service.services.audit_service import AdminAuditService

router = APIRouter(prefix="/admin-audit-logs", tags=["admin-audit-logs"])


def _build_actor(admin: AdminUser | None) -> AdminAuditActor | None:
    if admin is None:
        return None
    return AdminAuditActor(uid=str(admin.uid), email=admin.email, name=admin.name, role=admin.role)


def _build_item(log: AdminAuditLog) -> AdminAuditLogItem:
    actor_admin = _build_actor(log.actor_admin)
    if actor_admin is None:
        raise ValueError("Audit log actor_admin must not be null")

    return AdminAuditLogItem(
        id=log.id,
        actor_admin=actor_admin,
        target_admin=_build_actor(log.target_admin),
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        status=log.status,
        reason=log.reason,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        before_data=log.before_data,
        after_data=log.after_data,
        created_at=log.created_at,
    )


@router.get("/", response_model=AdminAuditLogListResponse, summary="List admin audit logs")
async def list_admin_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: AdminAuditCategory = Query(default="all"),
    action: str | None = Query(default=None),
    actor_uid: int | None = Query(default=None),
    target_uid: int | None = Query(default=None),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminAuditLogListResponse:
    del current_admin
    logs, total = await AdminAuditService.list_logs(
        db,
        page=page,
        page_size=page_size,
        category=category,
        action=action,
        actor_uid=actor_uid,
        target_uid=target_uid,
    )
    return AdminAuditLogListResponse(
        code=200,
        message="success",
        data=AdminAuditLogListData(
            items=[_build_item(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )
