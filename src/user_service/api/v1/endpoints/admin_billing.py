"""Admin-facing user billing endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from admin_service.policies import require_super_admin
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.api import PaginatedResponse
from common.db import ListParams
from common.utils.timezone import now
from user_service.dependencies import get_db_session
from user_service.schemas import (
    AdminAdjustBalanceRequest,
    AdminApiCallLogItem,
    AdminBalanceTransactionItem,
    AdminTopupRequest,
    AdminTopupOrderItem,
    AdminUsageStatItem,
    ApiResponse,
    AuthBaseResponse,
)
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService

router = APIRouter(prefix="/admin", tags=["admin-billing"])


def _build_list_params(
    *,
    page: int = 1,
    page_size: int = 20,
    start: datetime | None = None,
    end: datetime | None = None,
    time_field: str | None = None,
    order_by: str | None = None,
    default_days: int = 30,
) -> ListParams:
    params = ListParams(
        page=page,
        page_size=page_size,
        order_by=order_by,
        time_field=time_field,
        start=start,
        end=end,
    )
    if time_field is not None:
        params.validate_time_range(default_end=now(), default_days=default_days)
    return params


@router.post("/users/{uid}/topup", response_model=ApiResponse[AdminTopupOrderItem], summary="Manual top-up")
async def topup_user(
    uid: int,
    payload: AdminTopupRequest,
    current_admin: Any = Depends(require_super_admin),
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
    current_admin: Any = Depends(require_super_admin),
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
    response_model=ApiResponse[PaginatedResponse[AdminTopupOrderItem]],
    summary="List all top-up orders",
)
async def list_all_topup_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    status: int | None = None,
    _current_admin: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await TopupOrderService.get_all_orders(
        db,
        params=_build_list_params(page=page, page_size=page_size, order_by="created_at"),
        user_id=user_id,
        status=status,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AdminTopupOrderItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.get(
    "/users/{uid}/transactions",
    response_model=ApiResponse[PaginatedResponse[AdminBalanceTransactionItem]],
    summary="List user balance transactions",
)
async def list_user_transactions(
    uid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_admin: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await BalanceService.get_user_by_uid(db, uid)
    result = await BalanceService.list_transactions(
        db,
        user_id=int(user.id),
        params=_build_list_params(page=page, page_size=page_size, order_by="created_at"),
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AdminBalanceTransactionItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.get(
    "/usage/logs",
    response_model=ApiResponse[PaginatedResponse[AdminApiCallLogItem]],
    summary="List all API call logs",
)
async def list_admin_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    model_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _current_admin: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await UsageStatService.list_usage_logs(
        db,
        params=_build_list_params(
            page=page,
            page_size=page_size,
            start=start,
            end=end,
            time_field="created_at",
            order_by="created_at",
        ),
        user_id=user_id,
        model_name=model_name,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [AdminApiCallLogItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.get("/usage/stats", response_model=ApiResponse[list[AdminUsageStatItem]], summary="List all usage stats")
async def list_admin_usage_stats(
    start: datetime | None = None,
    end: datetime | None = None,
    user_id: int | None = None,
    model_name: str | None = None,
    _current_admin: Any = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    params = _build_list_params(start=start, end=end, time_field="stat_hour")
    items = await UsageStatService.get_all_stats(
        db,
        start=params.start,
        end=params.end,
        user_id=user_id,
        model_name=model_name,
    )
    return {
        "code": 200,
        "message": "success",
        "data": [AdminUsageStatItem.model_validate(item) for item in items],
    }
