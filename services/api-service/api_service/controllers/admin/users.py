"""Admin-facing user management endpoints — proxy elimination.

Ported from services/admin-service/src/controllers/user_management.py.
All gateway calls replaced with AdminEndUserService direct calls.
All safe_audit_commit replaced with inline AdminAuditService.record + db.commit().
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.schemas import BaseResponse
from api_service.core.db import get_db
from api_service.core.dependencies.admin import get_request_meta
from api_service.core.policies import require_active_admin, require_super_admin
from api_service.models import AdminUser
from api_service.schemas.admin.user_management import (
    AdjustUserBalanceRequest,
    ResetUserPasswordRequest,
    TopupUserRequest,
    UpdateUserRpmRequest,
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
    UserUsageAnalyticsBucket,
    UserUsageAnalyticsBucketCost,
    UserUsageAnalyticsData,
    UserUsageAnalyticsModel,
    UserUsageAnalyticsOverview,
    UserUsageAnalyticsResponse,
    UserUsageLogItem,
    UserUsageLogListResponse,
    UserUsageStatItem,
    UserUsageStatListResponse,
)
from api_service.services.admin.admin_user_service import AdminEndUserService
from api_service.services.admin.audit_service import AdminAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["admin-user-management"])


@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: int | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    items, total = await AdminEndUserService.list_users(
        db, page=page, page_size=page_size, search=search, status=status,
    )
    return UserListResponse(
        data={
            "items": [
                UserListItem.model_validate(u, from_attributes=True).model_dump(mode="json")
                for u in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/{uid}", response_model=UserDetailResponse, summary="User detail")
async def get_user_detail(
    uid: str,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserDetailResponse:
    from api_service.services.admin.admin_user_service import _UserNotFound

    try:
        data = await AdminEndUserService.get_user_detail(db, target_uid=uid)
    except _UserNotFound:
        raise HTTPException(status_code=404, detail="User not found")
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
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    result = await AdminEndUserService.update_user_status(db, target_uid=uid, status=payload.status)
    ip_address, user_agent = get_request_meta(request)
    action = "enable_user" if payload.status == 1 else "disable_user"
    await AdminAuditService.record(
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
    await db.commit()
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
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    await AdminEndUserService.reset_user_password(db, target_uid=uid, new_password=payload.new_password)
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
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
    await db.commit()
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
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    result = await AdminEndUserService.topup_user(
        db,
        target_uid=uid,
        amount=payload.amount,
        operator_admin=current_admin,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
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
    await db.commit()
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
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    await AdminEndUserService.adjust_user_balance(
        db,
        target_uid=uid,
        delta=payload.amount,
        operator_admin=current_admin,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
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
    await db.commit()
    return UserOperationResponse(message="余额调整成功")


@router.post(
    "/{uid}/rpm",
    response_model=UserOperationResponse,
    summary="Update per-user RPM override",
)
async def update_user_rpm(
    uid: str,
    payload: UpdateUserRpmRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    result = await AdminEndUserService.update_user_rpm(db, target_uid=uid, rpm_limit=payload.rpm_limit)
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="update_user_rpm",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        before_data={"rpm_limit": result.get("before_rpm_limit")},
        after_data={"rpm_limit": result.get("after_rpm_limit"), "remark": payload.remark},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    if payload.rpm_limit is None:
        return UserOperationResponse(message="已清除 RPM 覆盖，恢复使用全局默认值")
    return UserOperationResponse(message=f"RPM 已更新为 {payload.rpm_limit}")


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
    db: AsyncSession = Depends(get_db),
) -> UserTransactionListResponse:
    items, total = await AdminEndUserService.list_user_transactions(
        db, target_uid=uid, page=page, page_size=page_size,
    )
    return UserTransactionListResponse(
        data={
            "items": [
                UserTransactionItem.model_validate(t, from_attributes=True).model_dump(mode="json")
                for t in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/{uid}/api-keys", response_model=UserApiKeyListResponse, summary="List user API keys")
async def list_user_api_keys(
    uid: str,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserApiKeyListResponse:
    items = await AdminEndUserService.list_user_api_keys(db, target_uid=uid)
    return UserApiKeyListResponse(
        data=[UserApiKeyItem.model_validate(k, from_attributes=True).model_dump(mode="json") for k in items],
    )


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
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    await AdminEndUserService.disable_user_api_key(db, target_uid=uid, key_id=key_id)
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
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
    await db.commit()
    return UserOperationResponse(message="API Key 已禁用")


@router.post(
    "/{uid}/api-keys/{key_id}/enable",
    response_model=UserOperationResponse,
    summary="Enable user API key",
)
async def enable_user_api_key(
    uid: str,
    key_id: int,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOperationResponse:
    await AdminEndUserService.enable_user_api_key(db, target_uid=uid, key_id=key_id)
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="enable_user_api_key",
        resource_type="user",
        resource_id=str(uid),
        status="success",
        after_data={"key_id": key_id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return UserOperationResponse(message="API Key 已启用")


@router.get("/usage/logs", response_model=UserUsageLogListResponse, summary="List usage logs")
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_uid: str | None = None,
    model_name: str | None = None,
    request_id: str | None = None,
    api_key_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserUsageLogListResponse:
    items, total = await AdminEndUserService.list_user_usage_logs(
        db,
        target_uid=user_uid,
        page=page,
        page_size=page_size,
        model_name=model_name,
        request_id=request_id,
        api_key_id=api_key_id,
        start=start,
        end=end,
    )
    return UserUsageLogListResponse(
        data={
            "items": [
                UserUsageLogItem.model_validate(i, from_attributes=True).model_dump(mode="json")
                for i in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/usage/stats", response_model=UserUsageStatListResponse, summary="List usage stats")
async def list_usage_stats(
    user_uid: str | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserUsageStatListResponse:
    items = await AdminEndUserService.list_user_usage_stats(
        db,
        target_uid=user_uid,
        model_name=model_name,
        api_key_id=api_key_id,
        start=start,
        end=end,
    )
    return UserUsageStatListResponse(
        data=[UserUsageStatItem.model_validate(i, from_attributes=True).model_dump(mode="json") for i in items],
    )


@router.get(
    "/{uid}/usage/analytics",
    response_model=UserUsageAnalyticsResponse,
    summary="Get user usage analytics by uid",
)
async def get_user_usage_analytics(
    uid: str,
    range: str | None = Query(None, alias="range"),
    start: datetime | None = None,
    end: datetime | None = None,
    api_key_id: int | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> UserUsageAnalyticsResponse:
    data = await AdminEndUserService.get_user_usage_analytics(
        db,
        target_uid=uid,
        range_name=range,
        start=start,
        end=end,
        api_key_id=api_key_id,
    )
    # data is a UsageAnalyticsData dataclass — convert to response schema
    return UserUsageAnalyticsResponse(
        data=UserUsageAnalyticsData(
            range=getattr(data, "range_label", None),
            granularity=getattr(data, "granularity", ""),
            start=getattr(data, "start", None),
            end=getattr(data, "end", None),
            currency=getattr(data, "currency", "micro_yuan"),
            overview=UserUsageAnalyticsOverview(
                total_requests=getattr(data.overview, "total_requests", 0) if hasattr(data, "overview") else 0,
                success_requests=getattr(data.overview, "success_requests", 0) if hasattr(data, "overview") else 0,
                success_rate=getattr(data.overview, "success_rate", 0.0) if hasattr(data, "overview") else 0.0,
                total_cost=getattr(data.overview, "total_cost", 0) if hasattr(data, "overview") else 0,
            ) if hasattr(data, "overview") else None,
            models=[
                UserUsageAnalyticsModel(
                    effective_model=m.effective_model,
                    request_count=m.request_count,
                    request_share=m.request_share,
                    total_cost=m.total_cost,
                )
                for m in (data.models if hasattr(data, "models") else [])
            ],
            buckets=[
                UserUsageAnalyticsBucket(
                    bucket_start=b.bucket_start,
                    label=b.label,
                    costs=[
                        UserUsageAnalyticsBucketCost(
                            effective_model=c.effective_model,
                            total_cost=c.total_cost,
                        )
                        for c in b.costs
                    ],
                )
                for b in (data.buckets if hasattr(data, "buckets") else [])
            ],
        ),
    )
