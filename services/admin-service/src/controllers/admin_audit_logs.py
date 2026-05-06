"""Admin audit log endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.api import PaginatedResponse
from core.dependencies import get_db_session
from core.policies import require_super_admin
from models import AdminAuditLog, AdminUser
from schemas import (
    AdminAuditActor,
    AdminAuditCategory,
    AdminAuditLogItem,
    AdminAuditLogListResponse,
    AdminAuditLogMetaData,
    AdminAuditLogMetaResponse,
)
from services.audit_service import AdminAuditService

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
        action_label=AdminAuditService.ACTION_LABELS.get(log.action, log.action),
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


@router.get("/meta", response_model=AdminAuditLogMetaResponse, summary="Audit log filter metadata")
async def get_audit_log_meta(
    current_admin: AdminUser = Depends(require_super_admin),
) -> AdminAuditLogMetaResponse:
    del current_admin
    return AdminAuditLogMetaResponse(
        code=200,
        message="success",
        data=AdminAuditLogMetaData(
            categories=list(AdminAuditService.CATEGORY_ACTIONS.keys()),
            action_labels=AdminAuditService.ACTION_LABELS,
        ),
    )


@router.get("", response_model=AdminAuditLogListResponse, summary="List admin audit logs")
async def list_admin_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: AdminAuditCategory = Query(default="all"),
    action: str | None = Query(default=None, max_length=100),
    actor_uid: str | None = Query(default=None),
    target_uid: str | None = Query(default=None),
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
        data=PaginatedResponse[AdminAuditLogItem](
            items=[_build_item(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )
