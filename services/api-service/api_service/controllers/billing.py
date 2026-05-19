"""User-facing billing endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.api.pagination import PaginatedResponse
from api_service.common.infra.db.query import ListParams
from api_service.common.utils.timezone import now
from api_service.core.db import get_db
from api_service.models import User
from api_service.core.policies import require_active_user
from api_service.common.schemas import ApiResponse
from api_service.schemas.billing import (
    ApiCallLogItem,
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
from api_service.services.api_key_service import ApiKeyService
from api_service.services.balance_service import BalanceService
from api_service.services.topup_order_service import TopupOrderService
from api_service.services.usage_stat_service import UsageStatService
from api_service.services.voucher_service import VoucherService

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)

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
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        balance = await BalanceService.get_balance(db, int(current_user.id))
    except Exception:
        logger.exception("查询余额失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await BalanceService.list_transactions(
            db,
            user_id=int(current_user.id),
            params=ListParams(page=page, page_size=page_size, order_by="created_at"),
            tx_type=type,
        )
    except Exception:
        logger.exception("查询交易流水失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await VoucherService.list_user_redemptions(
            db,
            user_id=int(current_user.id),
            params=ListParams(page=page, page_size=page_size, order_by="redeemed_at"),
        )
    except Exception:
        logger.exception("查询代金券兑换记录失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        redeemed = await VoucherService.redeem_code(
            db,
            user_id=int(current_user.id),
            raw_code=payload.code,
        )
    except Exception:
        logger.exception("代金券兑换失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await TopupOrderService.get_user_orders(
            db,
            user_id=int(current_user.id),
            params=ListParams(page=page, page_size=page_size, order_by="created_at"),
        )
    except Exception:
        logger.exception("查询充值订单失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    if api_key_id is not None:
        await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
    params = _build_list_params(start=start, end=end, time_field="stat_hour")
    try:
        items = await UsageStatService.get_user_stats(
            db,
            user_id=int(current_user.id),
            start=params.start,
            end=params.end,
            model_name=model_name,
            api_key_id=api_key_id,
        )
    except Exception:
        logger.exception("查询用量统计失败")
        raise
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
    range: UsageAnalyticsRange | None = Query(None),
    start: datetime | None = None,
    end: datetime | None = None,
    api_key_id: int | None = None,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if api_key_id is not None:
        await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
    effective_start = start
    effective_end = end
    if start is not None or end is not None:
        params = _build_list_params(start=start, end=end, time_field="created_at")
        effective_start = params.start
        effective_end = params.end
    try:
        analytics = await UsageStatService.get_usage_analytics(
            db,
            user_id=int(current_user.id),
            range_name=range if effective_start is None else None,
            start=effective_start,
            end=effective_end,
            api_key_id=api_key_id,
        )
    except Exception:
        logger.exception("查询用量分析失败")
        raise
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    if api_key_id is not None:
        await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
    params = _build_list_params(
        page=page,
        page_size=page_size,
        start=start,
        end=end,
        time_field="created_at",
        order_by="created_at",
    )
    try:
        result = await UsageStatService.list_usage_logs(
            db,
            params=params,
            user_id=int(current_user.id),
            model_name=model_name,
            effective_model=effective_model,
            api_key_id=api_key_id,
            request_id=request_id,
        )
    except Exception:
        logger.exception("查询调用日志失败")
        raise
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [ApiCallLogItem.from_orm_instance(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        },
    }
