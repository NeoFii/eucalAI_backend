"""Admin audit log endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.api import PaginatedResponse
from common.core.exceptions import NotFoundException
from core.dependencies import get_db_session
from core.enums import AdminRole
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
from schemas.audit_log import UpdateActionLabelRequest, UpdateActionLabelResponse
from services.audit_service import AdminAuditService

router = APIRouter(prefix="/admin-audit-logs", tags=["admin-audit-logs"])


_ROLE_NAMES = {AdminRole.ADMIN: "admin", AdminRole.SUPER_ADMIN: "super_admin"}


def _build_actor(admin: AdminUser | None) -> AdminAuditActor | None:
    if admin is None:
        return None
    return AdminAuditActor(
        uid=str(admin.uid),
        email=admin.email,
        name=admin.name,
        role=_ROLE_NAMES.get(admin.role, "admin"),
    )


def _build_item(log: AdminAuditLog, action_labels: dict[str, str]) -> AdminAuditLogItem:
    actor_admin = _build_actor(log.actor_admin)
    if actor_admin is None:
        raise ValueError("Audit log actor_admin must not be null")

    return AdminAuditLogItem(
        id=log.id,
        actor_admin=actor_admin,
        target_admin=_build_actor(log.target_admin),
        action=log.action,
        action_label=action_labels.get(log.action, log.action),
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
    db: AsyncSession = Depends(get_db_session),
) -> AdminAuditLogMetaResponse:
    del current_admin
    categories, action_labels = await AdminAuditService.get_meta(db)
    return AdminAuditLogMetaResponse(
        code=200,
        message="success",
        data=AdminAuditLogMetaData(
            categories=categories,
            action_labels=action_labels,
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
    action_labels = await AdminAuditService.get_action_labels(db)
    return AdminAuditLogListResponse(
        code=200,
        message="success",
        data=PaginatedResponse[AdminAuditLogItem](
            items=[_build_item(log, action_labels) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.patch(
    "/action-definitions/{code}",
    response_model=UpdateActionLabelResponse,
    summary="Update action definition label",
)
async def update_action_label(
    code: str,
    body: UpdateActionLabelRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UpdateActionLabelResponse:
    del current_admin
    action_def = await AdminAuditService.update_action_label(db, code, body.label)
    if action_def is None:
        raise NotFoundException(f"Action definition '{code}' not found")
    return UpdateActionLabelResponse(
        code=200,
        message="success",
        data={"code": action_def.code, "label": action_def.label},
    )
