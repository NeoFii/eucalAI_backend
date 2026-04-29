"""Admin-facing user management endpoints (facade over user-service).

These endpoints proxy user operations to user-service via the gateway layer.
They belong to the admin control-plane facade, not the admin domain proper.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session, get_request_meta
from admin_service.gateway import UserManagementGateway
from admin_service.models import AdminUser
from admin_service.policies import require_active_admin, require_super_admin
from admin_service.schemas.user_management import (
    AdjustUserBalanceRequest,
    ResetUserPasswordRequest,
    TopupUserRequest,
    UpdateUserStatusRequest,
    UserApiKeyItem,
    UserApiKeyListResponse,
    UserDetailData,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
    UserOperationResponse,
    UserTransactionItem,
    UserTransactionListResponse,
    UserUsageLogItem,
    UserUsageLogListResponse,
    UserUsageStatItem,
    UserUsageStatListResponse,
)
from admin_service.services.audit_service import AdminAuditService
from common.api import PaginatedResponse
from common.utils.timezone import format_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["user-management"])

_gateway = UserManagementGateway()


async def _safe_audit_commit(
    db: AsyncSession,
    **audit_kwargs,
) -> None:
    """Write an audit record and commit. On failure, log the full audit payload
    at CRITICAL level so it can be recovered from logs."""
    try:
        await AdminAuditService.record(db, **audit_kwargs)
        await db.commit()
    except Exception:
        logger.critical(
            "Audit commit failed after successful gateway operation: %s",
            json.dumps(audit_kwargs, default=str),
        )
        await db.rollback()


@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: int | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserListResponse:
    data = await _gateway.list_users(
        page=page, page_size=page_size, search=search, status=status,
    )
    return UserListResponse(
        data=PaginatedResponse[UserListItem](
            items=[UserListItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        ),
    )


@router.get("/{uid}", response_model=UserDetailResponse, summary="User detail")
async def get_user_detail(
    uid: str,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserDetailResponse:
    data = await _gateway.get_user_detail(uid)
    return UserDetailResponse(data=UserDetailData(**data))


@router.post(
    "/{uid}/status",
    response_model=UserOperationResponse,
    summary="Enable/disable user",
)
async def update_user_status(
    uid: str,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserOperationResponse:
    result = await _gateway.update_user_status(uid, payload.status)
    ip_address, user_agent = get_request_meta(request)
    action = "enable_user" if payload.status == 1 else "disable_user"
    await _safe_audit_commit(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action=action,
        resource_type="user",
        resource_id=str(uid),
        status="success",
        before_data={"status": result["before_status"]},
        after_data={"status": result["after_status"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserOperationResponse(message="操作成功")


@router.post(
    "/{uid}/reset-password",
    response_model=UserOperationResponse,
    summary="Reset user password",
)
async def reset_user_password(
    uid: str,
    payload: ResetUserPasswordRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserOperationResponse:
    await _gateway.reset_user_password(uid, payload.new_password)
    ip_address, user_agent = get_request_meta(request)
    await _safe_audit_commit(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="reset_user_password",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserOperationResponse(message="密码重置成功")


@router.post(
    "/{uid}/topup",
    response_model=UserOperationResponse,
    summary="Manual topup",
)
async def topup_user(
    uid: str,
    payload: TopupUserRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserOperationResponse:
    result = await _gateway.topup_user(
        uid,
        amount=payload.amount,
        operator_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await _safe_audit_commit(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="topup_user",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        after_data={"amount": payload.amount, "order_no": result.get("order_no")},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserOperationResponse(message="充值成功")


@router.post(
    "/{uid}/adjust-balance",
    response_model=UserOperationResponse,
    summary="Adjust user balance",
)
async def adjust_user_balance(
    uid: str,
    payload: AdjustUserBalanceRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserOperationResponse:
    await _gateway.adjust_user_balance(
        uid,
        amount=payload.amount,
        operator_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await _safe_audit_commit(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="adjust_user_balance",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        after_data={"amount": payload.amount, "remark": payload.remark},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserOperationResponse(message="余额调整成功")


@router.get(
    "/{uid}/transactions",
    response_model=UserTransactionListResponse,
    summary="List user transactions",
)
async def list_user_transactions(
    uid: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserTransactionListResponse:
    data = await _gateway.list_user_transactions(uid, page=page, page_size=page_size)
    return UserTransactionListResponse(
        data=PaginatedResponse[UserTransactionItem](
            items=[UserTransactionItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        ),
    )


@router.get("/{uid}/api-keys", response_model=UserApiKeyListResponse, summary="List user API keys")
async def list_user_api_keys(
    uid: str,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserApiKeyListResponse:
    items = await _gateway.list_user_api_keys(uid)
    return UserApiKeyListResponse(data=[UserApiKeyItem(**item) for item in items])


@router.post(
    "/{uid}/api-keys/{key_id}/disable",
    response_model=UserOperationResponse,
    summary="Disable user API key",
)
async def disable_user_api_key(
    uid: str,
    key_id: int,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserOperationResponse:
    await _gateway.disable_user_api_key(uid, key_id)
    ip_address, user_agent = get_request_meta(request)
    await _safe_audit_commit(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="disable_user_api_key",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        after_data={"key_id": key_id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return UserOperationResponse(message="API Key 已禁用")


@router.get("/usage/logs", response_model=UserUsageLogListResponse, summary="List usage logs")
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    model_name: str | None = None,
    request_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserUsageLogListResponse:
    data = await _gateway.list_usage_logs(
        page=page,
        page_size=page_size,
        user_id=user_id,
        model_name=model_name,
        request_id=request_id,
        start=format_iso(start),
        end=format_iso(end),
    )
    return UserUsageLogListResponse(
        data=PaginatedResponse[UserUsageLogItem](
            items=[UserUsageLogItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        ),
    )


@router.get("/usage/stats", response_model=UserUsageStatListResponse, summary="List usage stats")
async def list_usage_stats(
    user_id: int | None = None,
    model_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserUsageStatListResponse:
    items = await _gateway.list_usage_stats(
        user_id=user_id,
        model_name=model_name,
        start=format_iso(start),
        end=format_iso(end),
    )
    return UserUsageStatListResponse(data=[UserUsageStatItem(**item) for item in items])
