"""User-facing billing endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.api import PaginatedResponse
from common.db import ListParams
from common.utils.timezone import now
from user_service.dependencies import get_db_session
from user_service.models import User
from user_service.policies import require_active_user
from user_service.schemas import (
    ApiCallLogItem,
    ApiResponse,
    BalanceResponseData,
    BalanceTransactionItem,
    TopupOrderItem,
    UsageAnalyticsData,
    UsageAnalyticsRange,
    UsageStatItem,
    VoucherRedeemRequest,
    VoucherRedeemResponseData,
    VoucherRedemptionItem,
)
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService
from user_service.services.voucher_service import VoucherService

router = APIRouter(prefix="/billing", tags=["billing"])

DEFAULT_BILLING_LOOKBACK_DAYS = 30
MAX_BILLING_RANGE_DAYS = 90


def _build_list_params(
    *,
    page: int = 1,
    page_size: int = 20,
    start: datetime | None = None,
    end: datetime | None = None,
    time_field: str | None = None,
    default_days: int = DEFAULT_BILLING_LOOKBACK_DAYS,
    order_by: str | None = None,
) -> ListParams:
    params = ListParams(
        page=page,
        page_size=page_size,
        order_by=order_by,
        time_field=time_field,
        start=start,
        end=end,
        max_span_days=MAX_BILLING_RANGE_DAYS,
    )
    if time_field is not None:
        params.validate_time_range(default_end=now(), default_days=default_days)
    return params


@router.get("/balance", response_model=ApiResponse[BalanceResponseData], summary="Get current balance")
async def get_balance(
    current_user: User = Depends(require_active_user),
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
    response_model=ApiResponse[PaginatedResponse[BalanceTransactionItem]],
    summary="List balance transactions",
)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    type: int | None = Query(None, ge=1, le=7),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await BalanceService.list_transactions(
        db,
        user_id=int(current_user.id),
        params=ListParams(page=page, page_size=page_size, order_by="created_at"),
        tx_type=type,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [BalanceTransactionItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.get(
    "/vouchers/redemptions",
    response_model=ApiResponse[PaginatedResponse[VoucherRedemptionItem]],
    summary="List voucher redemptions",
)
async def list_voucher_redemptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await VoucherService.list_user_redemptions(
        db,
        user_id=int(current_user.id),
        params=ListParams(page=page, page_size=page_size, order_by="redeemed_at"),
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [VoucherRedemptionItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.post(
    "/vouchers/redeem",
    response_model=ApiResponse[VoucherRedeemResponseData],
    summary="Redeem voucher code",
)
async def redeem_voucher_code(
    payload: VoucherRedeemRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    redeemed = await VoucherService.redeem_code(
        db,
        user_id=int(current_user.id),
        raw_code=payload.code,
    )
    return {
        "code": 200,
        "message": "success",
        "data": VoucherRedeemResponseData.model_validate(redeemed),
    }


@router.get(
    "/topup-orders",
    response_model=ApiResponse[PaginatedResponse[TopupOrderItem]],
    summary="List top-up orders",
)
async def list_topup_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await TopupOrderService.get_user_orders(
        db,
        user_id=int(current_user.id),
        params=ListParams(page=page, page_size=page_size, order_by="created_at"),
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [TopupOrderItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }


@router.get(
    "/usage",
    response_model=ApiResponse[list[UsageStatItem]],
    summary="List usage stats",
    description="Hourly aggregate usage stats. Token and cost data may be partial (stream tokens and cost not yet populated).",
)
async def list_usage_stats(
    start: datetime | None = None,
    end: datetime | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    params = _build_list_params(start=start, end=end, time_field="stat_hour")
    items = await UsageStatService.get_user_stats(
        db,
        user_id=int(current_user.id),
        start=params.start,
        end=params.end,
        model_name=model_name,
        api_key_id=api_key_id,
    )
    return {
        "code": 200,
        "message": "success",
        "data": [UsageStatItem.model_validate(item) for item in items],
    }


@router.get(
    "/usage/analytics",
    response_model=ApiResponse[UsageAnalyticsData],
    summary="Get usage analytics",
)
async def list_usage_analytics(
    range: UsageAnalyticsRange = Query("8h"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    analytics = await UsageStatService.get_usage_analytics(
        db,
        user_id=int(current_user.id),
        range_name=range,
    )
    return {
        "code": 200,
        "message": "success",
        "data": analytics,
    }


@router.get(
    "/usage/logs",
    response_model=ApiResponse[PaginatedResponse[ApiCallLogItem]],
    summary="List usage logs",
)
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start: datetime | None = None,
    end: datetime | None = None,
    model_name: str | None = None,
    effective_model: str | None = None,
    api_key_id: int | None = None,
    request_id: str | None = None,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    params = _build_list_params(
        page=page,
        page_size=page_size,
        start=start,
        end=end,
        time_field="created_at",
        order_by="created_at",
    )
    result = await UsageStatService.list_usage_logs(
        db,
        params=params,
        user_id=int(current_user.id),
        model_name=model_name,
        effective_model=effective_model,
        api_key_id=api_key_id,
        request_id=request_id,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [ApiCallLogItem.model_validate(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }
