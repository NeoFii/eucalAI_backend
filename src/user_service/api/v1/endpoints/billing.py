"""User-facing billing endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import ValidationException
from common.utils.timezone import now
from user_service.dependencies import get_current_user, get_db_session
from user_service.models import User
from user_service.schemas import (
    ApiCallLogItem,
    ApiResponse,
    BalanceResponseData,
    BalanceTransactionItem,
    ListResponse,
    TopupOrderItem,
    UsageStatItem,
)
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService

router = APIRouter(prefix="/billing", tags=["billing"])

DEFAULT_BILLING_LOOKBACK_DAYS = 30
MAX_BILLING_RANGE_DAYS = 90


def _resolve_time_window(
    start: datetime | None,
    end: datetime | None,
    *,
    default_days: int = DEFAULT_BILLING_LOOKBACK_DAYS,
    max_days: int = MAX_BILLING_RANGE_DAYS,
) -> tuple[datetime, datetime]:
    effective_end = end or now()
    effective_start = start or (effective_end - timedelta(days=default_days))
    if effective_start >= effective_end:
        raise ValidationException(detail="开始时间必须早于结束时间")
    if effective_end - effective_start > timedelta(days=max_days):
        raise ValidationException(detail=f"时间范围不能超过 {max_days} 天")
    return effective_start, effective_end


@router.get("/balance", response_model=ApiResponse[BalanceResponseData], summary="Get current balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    balance = await BalanceService.get_balance(db, int(current_user.id))
    return {
        "code": 200,
        "message": "success",
        "data": BalanceResponseData(
            balance=balance["balance"],
            frozen_amount=balance["frozen_amount"],
            used_amount=balance["used_amount"],
            total_requests=balance["total_requests"],
            total_tokens=balance["total_tokens"],
        ),
    }


@router.get(
    "/transactions",
    response_model=ApiResponse[ListResponse[BalanceTransactionItem]],
    summary="List balance transactions",
)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, total = await BalanceService.list_transactions(
        db,
        user_id=int(current_user.id),
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
    "/topup-orders",
    response_model=ApiResponse[ListResponse[TopupOrderItem]],
    summary="List top-up orders",
)
async def list_topup_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, total = await TopupOrderService.get_user_orders(
        db,
        user_id=int(current_user.id),
        page=page,
        page_size=page_size,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [TopupOrderItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/usage", response_model=ApiResponse[list[UsageStatItem]], summary="List usage stats")
async def list_usage_stats(
    start: datetime | None = None,
    end: datetime | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    effective_start, effective_end = _resolve_time_window(start, end)
    items = await UsageStatService.get_user_stats(
        db,
        user_id=int(current_user.id),
        start=effective_start,
        end=effective_end,
        model_name=model_name,
        api_key_id=api_key_id,
    )
    return {
        "code": 200,
        "message": "success",
        "data": [UsageStatItem.model_validate(item) for item in items],
    }


@router.get(
    "/usage/logs",
    response_model=ApiResponse[ListResponse[ApiCallLogItem]],
    summary="List usage logs",
)
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start: datetime | None = None,
    end: datetime | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    effective_start, effective_end = _resolve_time_window(start, end)
    items, total = await UsageStatService.list_usage_logs(
        db,
        user_id=int(current_user.id),
        start=effective_start,
        end=effective_end,
        model_name=model_name,
        api_key_id=api_key_id,
        page=page,
        page_size=page_size,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [ApiCallLogItem.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
