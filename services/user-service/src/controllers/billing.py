"""User-facing billing endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.api import PaginatedResponse
from common.core.exceptions import NotFoundException, ServiceException
from common.db import ListParams
from common.observability import log_event
from common.utils.timezone import now
from core.config import settings
from core.dependencies import get_db_session
from models import User
from core.policies import require_active_user
from repositories import TopupOrderRepository
from schemas import (
    AlipayCreateOrderRequest,
    AlipayCreateOrderResponse,
    AlipayOrderStatusResponse,
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
from services.alipay_service import AlipayService
from services.api_key_service import ApiKeyService
from services.balance_service import BalanceService
from services.topup_order_service import TopupOrderService
from services.usage_stat_service import UsageStatService
from services.voucher_service import VoucherService

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
    if api_key_id is not None:
        await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
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
    range: UsageAnalyticsRange | None = Query(None),
    start: datetime | None = None,
    end: datetime | None = None,
    api_key_id: int | None = None,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if api_key_id is not None:
        await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
    effective_start = start
    effective_end = end
    if start is not None or end is not None:
        params = _build_list_params(start=start, end=end, time_field="created_at")
        effective_start = params.start
        effective_end = params.end
    analytics = await UsageStatService.get_usage_analytics(
        db,
        user_id=int(current_user.id),
        range_name=range if effective_start is None else None,
        start=effective_start,
        end=effective_end,
        api_key_id=api_key_id,
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


# --- Alipay Payment Endpoints ---


@router.post(
    "/alipay/create-order",
    response_model=ApiResponse[AlipayCreateOrderResponse],
    summary="Create Alipay payment order",
)
async def alipay_create_order(
    payload: AlipayCreateOrderRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    order = await TopupOrderService.create_alipay_order(
        db, user_id=int(current_user.id), amount=payload.amount
    )
    subject = f"Eucal AI 余额充值 - {order.order_no}"
    if payload.device == "mobile":
        form_html = AlipayService.create_wap_pay(order.order_no, payload.amount, subject)
    else:
        form_html = AlipayService.create_page_pay(order.order_no, payload.amount, subject)
    return {
        "code": 200,
        "message": "success",
        "data": AlipayCreateOrderResponse(order_no=order.order_no, form_html=form_html),
    }


@router.post(
    "/alipay/precreate",
    response_model=ApiResponse[dict],
    summary="Create Alipay QR code payment",
)
async def alipay_precreate(
    payload: AlipayCreateOrderRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    order = await TopupOrderService.create_alipay_order(
        db, user_id=int(current_user.id), amount=payload.amount
    )
    subject = f"Eucal AI 余额充值 - {order.order_no}"
    qr_url = await AlipayService.precreate(order.order_no, payload.amount, subject)
    if not qr_url:
        raise ServiceException(detail="创建支付二维码失败，请稍后重试")
    return {
        "code": 200,
        "message": "success",
        "data": {"order_no": order.order_no, "qr_url": qr_url},
    }


@router.post("/alipay/notify", summary="Alipay async notification handler")
async def alipay_notify(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> PlainTextResponse:
    body = await request.body()
    params: dict[str, str] = {}
    for pair in body.decode("utf-8").split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = unquote_plus(v)

    if not AlipayService.verify_notify(params):
        log_event(logger, logging.WARNING, "alipayNotifyVerifyFailed")
        return PlainTextResponse("failure")

    # Validate app_id
    if params.get("app_id") != settings.ALIPAY_APP_ID:
        log_event(logger, logging.WARNING, "alipayNotifyAppIdMismatch")
        return PlainTextResponse("failure")

    trade_status = params.get("trade_status", "")
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return PlainTextResponse("success")

    out_trade_no = params.get("out_trade_no", "")
    trade_no = params.get("trade_no", "")
    total_amount = params.get("total_amount", "")

    repo = TopupOrderRepository(db)
    order = await repo.get_by_order_no(order_no=out_trade_no, for_update=True)
    if order is None:
        log_event(logger, logging.WARNING, "alipayNotifyOrderNotFound", order_no=out_trade_no)
        return PlainTextResponse("success")

    # Already processed — idempotent
    if order.status != order.STATUS_PENDING:
        return PlainTextResponse("success")

    # Verify amount matches
    expected_yuan = str(Decimal(int(order.amount)) / Decimal(1_000_000))
    if total_amount != expected_yuan:
        log_event(
            logger, logging.WARNING, "alipayNotifyAmountMismatch",
            order_no=out_trade_no, expected=expected_yuan, got=total_amount,
        )
        return PlainTextResponse("failure")

    await TopupOrderService.mark_paid(db, order, payment_no=trade_no, payment_raw=params)
    return PlainTextResponse("success")


@router.get("/alipay/return", summary="Alipay sync return redirect")
async def alipay_return(request: Request) -> RedirectResponse:
    order_no = request.query_params.get("out_trade_no", "")
    return_url = settings.ALIPAY_RETURN_URL.rsplit("/api/", 1)[0]
    redirect_target = f"{return_url}/console/payment/recharge/result?order_no={order_no}"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.get(
    "/alipay/order/{order_no}/status",
    response_model=ApiResponse[AlipayOrderStatusResponse],
    summary="Query Alipay order status",
)
async def alipay_order_status(
    order_no: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    repo = TopupOrderRepository(db)
    order = await repo.get_for_user_by_order_no(
        order_no=order_no, user_id=int(current_user.id)
    )
    if order is None:
        raise NotFoundException(detail="订单不存在")

    # If still pending, try querying Alipay for latest status
    if order.status == order.STATUS_PENDING:
        trade_info = await AlipayService.query_trade(order_no)
        if trade_info and trade_info.get("trade_status") in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            await TopupOrderService.mark_paid(
                db, order,
                payment_no=trade_info["trade_no"],
                payment_raw=trade_info,
            )

    return {
        "code": 200,
        "message": "success",
        "data": AlipayOrderStatusResponse(
            order_no=order.order_no,
            status=order.status,
            amount=int(order.amount),
            paid_at=order.paid_at,
        ),
    }
