"""Admin-facing user billing endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from admin_service.dependencies import require_super_admin
from admin_service.models import AdminUser
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from user_service.dependencies import get_db_session
from user_service.schemas import (
    AdminAdjustBalanceRequest,
    AdminApiCallLogItem,
    AdminTopupRequest,
    AdminTopupOrderItem,
    AdminUsageStatItem,
    ApiResponse,
    AuthBaseResponse,
    BalanceTransactionItem,
    ListResponse,
)
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService

router = APIRouter(prefix="/admin", tags=["admin-billing"])


@router.post("/users/{uid}/topup", response_model=ApiResponse[AdminTopupOrderItem], summary="Manual top-up")
async def topup_user(
    uid: int,
    payload: AdminTopupRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await BalanceService.get_user_by_uid(db, uid)
    order = await TopupOrderService.create_manual(
        db,
        user_id=int(user.id),
        amount=payload.amount,
        operator_id=int(current_admin.id),
        remark=payload.remark,
    )
    return {
        "code": 200,
        "message": "success",
        "data": AdminTopupOrderItem.model_validate(order),
    }


@router.post("/users/{uid}/adjust-balance", response_model=AuthBaseResponse, summary="Adjust user balance")
async def adjust_user_balance(
    uid: int,
    payload: AdminAdjustBalanceRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    user = await BalanceService.get_user_by_uid(db, uid)
    await BalanceService.admin_adjust(
        db,
        user_id=int(user.id),
        amount=payload.amount,
        operator_id=int(current_admin.id),
        remark=payload.remark,
    )
    return AuthBaseResponse(code=200, message="success")


@router.get(
    "/topup-orders",
    response_model=ApiResponse[ListResponse[AdminTopupOrderItem]],
    summary="List all top-up orders",
)
async def list_all_topup_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    status: int | None = None,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, total = await TopupOrderService.get_all_orders(
        db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        status=status,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AdminTopupOrderItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get(
    "/users/{uid}/transactions",
    response_model=ApiResponse[ListResponse[BalanceTransactionItem]],
    summary="List user balance transactions",
)
async def list_user_transactions(
    uid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await BalanceService.get_user_by_uid(db, uid)
    items, total = await BalanceService.list_transactions(
        db,
        user_id=int(user.id),
        page=page,
        page_size=page_size,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [BalanceTransactionItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get(
    "/usage/logs",
    response_model=ApiResponse[ListResponse[AdminApiCallLogItem]],
    summary="List all API call logs",
)
async def list_admin_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    model_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, total = await UsageStatService.list_usage_logs(
        db,
        user_id=user_id,
        model_name=model_name,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AdminApiCallLogItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/usage/stats", response_model=ApiResponse[list[AdminUsageStatItem]], summary="List all usage stats")
async def list_admin_usage_stats(
    start: datetime | None = None,
    end: datetime | None = None,
    user_id: int | None = None,
    model_name: str | None = None,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    effective_end = end or now()
    effective_start = start or (effective_end - timedelta(days=30))
    items = await UsageStatService.get_all_stats(
        db,
        start=effective_start,
        end=effective_end,
        user_id=user_id,
        model_name=model_name,
    )
    return {
        "code": 200,
        "message": "success",
        "data": [AdminUsageStatItem.model_validate(item) for item in items],
    }
