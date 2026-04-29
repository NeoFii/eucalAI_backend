"""Internal user-service endpoints."""

import hashlib
import logging
from datetime import datetime

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.internal import build_internal_auth_dependency
from common.utils.password import hash_password
from common.utils.timezone import now
from user_service.config import settings
from user_service.dependencies import get_db_session
from user_service.models.api_call_log import ApiCallLog
from user_service.models.balance_transaction import BalanceTransaction
from user_service.repositories.api_key_repository import ApiKeyRepository
from user_service.repositories.balance_tx_repository import BalanceTxRepository
from user_service.repositories.user_repository import UserRepository
from user_service.services.api_key_service import ApiKeyService
from user_service.services.auth_service import AuthService
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService
from user_service.services.voucher_service import VoucherService

logger = logging.getLogger("user_service.internal")

router = APIRouter(prefix="/internal", tags=["internal"])
verify_internal_secret = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"admin-service", "router-service"},
)
verify_router_only = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"router-service"},
)


class InternalUserResponse(BaseModel):
    id: int
    uid: str
    email: str
    status: int


class InternalUserStatsResponse(BaseModel):
    total_users: int


class InternalApiKeyValidateRequest(BaseModel):
    key: str
    model: str | None = None
    client_ip: str | None = None


class InternalApiKeyValidateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    balance: int
    rpm_limit: int | None = None


# --- Admin user-management schemas ---


class InternalUserListItem(BaseModel):
    uid: str
    email: str
    status: int
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    balance: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalUserListResponse(BaseModel):
    items: list[InternalUserListItem]
    total: int
    page: int
    page_size: int


class InternalUserDetailResponse(BaseModel):
    uid: str
    email: str
    status: int
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalUpdateStatusRequest(BaseModel):
    status: Literal[0, 1]


class InternalUpdateStatusResponse(BaseModel):
    uid: str
    before_status: int
    after_status: int


class InternalResetPasswordRequest(BaseModel):
    new_password: str


class InternalTopupRequest(BaseModel):
    amount: int = Field(gt=0, le=settings.MAX_TOPUP_AMOUNT)
    operator_uid: str  # admin NanoID uid, stored as operator_id in DB
    remark: str = Field(default="", max_length=255)


class InternalAdjustBalanceRequest(BaseModel):
    amount: int = Field(ge=-settings.MAX_TOPUP_AMOUNT, le=settings.MAX_TOPUP_AMOUNT)
    operator_uid: str  # admin NanoID uid, stored as operator_id in DB
    remark: str = Field(max_length=255)


class InternalTransactionItem(BaseModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: str | None = None
    ref_id: str | None = None
    remark: str | None = None
    operator_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalTransactionListResponse(BaseModel):
    items: list[InternalTransactionItem]
    total: int
    page: int
    page_size: int


class InternalApiKeyItem(BaseModel):
    id: int
    key_prefix: str
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: str | None = None
    allow_ips: str | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalUsageLogItem(BaseModel):
    id: int
    user_id: int
    request_id: str
    api_key_id: int | None = None
    model_name: str
    selected_model: str | None = None
    provider_slug: str | None = None
    upstream_model: str | None = None
    config_version: int | None = None
    config_source: str | None = None
    inference_config_version: int | None = None
    inference_config_source: str | None = None
    routing_tier: int | None = None
    score_source: str | None = None
    router_trace_id: str | None = None
    inference_error_code: str | None = None
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    cost: int
    status: int
    duration_ms: int | None = None
    is_stream: bool
    error_code: str | None = None
    error_msg: str | None = None
    ip: str | None = None
    cost_detail: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InternalUsageLogListResponse(BaseModel):
    items: list[InternalUsageLogItem]
    total: int
    page: int
    page_size: int


class InternalUsageStatItem(BaseModel):
    id: int
    user_id: int
    api_key_id: int | None = None
    model_name: str
    stat_hour: datetime
    request_count: int
    success_count: int
    error_count: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    total_tokens: int
    total_cost: int

    model_config = ConfigDict(from_attributes=True)


class InternalVoucherGenerateRequest(BaseModel):
    amount: int = Field(gt=0)
    count: int = Field(ge=1, le=1000)
    starts_at: datetime
    expires_at: datetime
    operator_uid: str | None = None
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("starts_at", "expires_at", mode="after")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        from common.utils.timezone import to_shanghai_naive

        return to_shanghai_naive(value)


class InternalVoucherDisableRequest(BaseModel):
    operator_uid: str | None = None


class InternalVoucherItem(BaseModel):
    id: int
    code_prefix: str
    code_suffix: str
    amount: int
    status: int
    starts_at: datetime
    expires_at: datetime
    redeemed_user_uid: str | None = None
    redeemed_at: datetime | None = None
    created_by_admin_uid: str | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalCreatedVoucherItem(InternalVoucherItem):
    code: str


class InternalVoucherCreateResponse(BaseModel):
    items: list[InternalCreatedVoucherItem]


class InternalVoucherListResponse(BaseModel):
    items: list[InternalVoucherItem]
    total: int
    page: int
    page_size: int


@router.get("/users/{uid}", response_model=InternalUserResponse, summary="Get user by uid")
async def get_user_by_uid(
    uid: str = Path(min_length=1),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserResponse:
    user = await UserRepository(db).get_by_uid(uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return InternalUserResponse(
        id=int(user.id),
        uid=user.uid,
        email=user.email,
        status=int(user.status),
    )


@router.post(
    "/api-keys/validate",
    response_model=InternalApiKeyValidateResponse,
    summary="Validate user API key",
)
async def validate_api_key(
    payload: InternalApiKeyValidateRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalApiKeyValidateResponse:
    key_hash = hashlib.sha256(payload.key.encode("utf-8")).hexdigest()
    api_key = await ApiKeyService.validate_by_hash(
        db,
        key_hash,
        model=payload.model,
        client_ip=payload.client_ip,
    )
    user = await UserRepository(db).get_by_id(api_key.user_id)
    return InternalApiKeyValidateResponse(
        id=int(api_key.id),
        user_id=int(api_key.user_id),
        name=api_key.name,
        balance=int(user.balance) if user else 0,
        rpm_limit=api_key.rpm_limit,
    )


@router.get("/stats/users", response_model=InternalUserStatsResponse, summary="Get user stats")
async def get_user_stats(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserStatsResponse:
    total_users = await UserRepository(db).count_all()
    return InternalUserStatsResponse(total_users=total_users)


@router.post("/vouchers", response_model=InternalVoucherCreateResponse, summary="Generate voucher codes")
async def generate_voucher_codes(
    payload: InternalVoucherGenerateRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalVoucherCreateResponse:
    generated = await VoucherService.generate_codes(
        db,
        amount=payload.amount,
        count=payload.count,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        created_by_admin_uid=payload.operator_uid,
        remark=payload.remark,
    )
    return InternalVoucherCreateResponse(
        items=[
            InternalCreatedVoucherItem(
                **InternalVoucherItem.model_validate(item.record).model_dump(),
                code=item.code,
            )
            for item in generated
        ]
    )


@router.get("/vouchers", response_model=InternalVoucherListResponse, summary="List vouchers")
async def list_vouchers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: int | None = Query(None, alias="status"),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalVoucherListResponse:
    result = await VoucherService.list_for_admin(
        db,
        params=ListParams(page=page, page_size=page_size, order_by="created_at"),
        status=status_filter,
    )
    return InternalVoucherListResponse(
        items=[InternalVoucherItem.model_validate(voucher) for voucher in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/vouchers/{voucher_id}", response_model=InternalVoucherItem, summary="Get voucher")
async def get_voucher(
    voucher_id: int = Path(gt=0),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalVoucherItem:
    voucher = await VoucherService.get(db, voucher_id)
    return InternalVoucherItem.model_validate(voucher)


@router.delete(
    "/vouchers/{voucher_id}",
    response_model=InternalVoucherItem,
    summary="Disable voucher code",
)
async def disable_voucher_code(
    voucher_id: int = Path(gt=0),
    payload: InternalVoucherDisableRequest = ...,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalVoucherItem:
    voucher = await VoucherService.disable(
        db,
        code_id=voucher_id,
        operator_id=payload.operator_uid,
    )
    return InternalVoucherItem.model_validate(voucher)


# --- Admin user-management endpoints ---


async def _get_user_or_404(db: AsyncSession, uid: str):
    user = await UserRepository(db).get_by_uid(uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users", response_model=InternalUserListResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status_filter: int | None = Query(None, alias="status"),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserListResponse:
    items, total = await UserRepository(db).list_users(
        page=page, page_size=page_size, search=search, status=status_filter,
    )
    return InternalUserListResponse(
        items=[InternalUserListItem.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/users/{uid}/detail",
    response_model=InternalUserDetailResponse,
    summary="Get user detail",
)
async def get_user_detail(
    uid: str = Path(min_length=1),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserDetailResponse:
    user = await _get_user_or_404(db, uid)
    return InternalUserDetailResponse.model_validate(user)


@router.post(
    "/users/{uid}/status",
    response_model=InternalUpdateStatusResponse,
    summary="Update user status",
)
async def update_user_status(
    uid: str = Path(min_length=1),
    payload: InternalUpdateStatusRequest = ...,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUpdateStatusResponse:
    user = await _get_user_or_404(db, uid)
    before_status = int(user.status)
    user.status = payload.status
    if payload.status == 0 and before_status != 0:
        await ApiKeyService.disable_all_for_user(db, int(user.id))
    await db.commit()
    return InternalUpdateStatusResponse(
        uid=user.uid, before_status=before_status, after_status=payload.status,
    )


@router.post("/users/{uid}/reset-password", summary="Reset user password")
async def reset_user_password(
    uid: str = Path(min_length=1),
    payload: InternalResetPasswordRequest = ...,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from user_service.utils.password import check_password_strength

    ok, msg = check_password_strength(payload.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg,
        )
    user = await _get_user_or_404(db, uid)
    user.password_hash = hash_password(payload.new_password)
    await AuthService._revoke_all_user_sessions(db, user.id)
    await db.commit()
    return {"uid": user.uid, "success": True}


@router.post("/users/{uid}/topup", summary="Manual topup")
async def topup_user(
    uid: str = Path(min_length=1),
    payload: InternalTopupRequest = ...,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    order = await TopupOrderService.create_manual(
        db,
        user_id=int(user.id),
        amount=payload.amount,
        operator_id=payload.operator_uid,
        remark=payload.remark,
    )
    return {
        "order_no": order.order_no,
        "amount": int(order.amount),
        "status": int(order.status),
    }


@router.post("/users/{uid}/adjust-balance", summary="Adjust user balance")
async def adjust_user_balance(
    uid: str = Path(min_length=1),
    payload: InternalAdjustBalanceRequest = ...,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    await BalanceService.admin_adjust(
        db,
        user_id=int(user.id),
        amount=payload.amount,
        operator_id=payload.operator_uid,
        remark=payload.remark,
    )
    return {"uid": user.uid, "success": True}


@router.get(
    "/users/{uid}/transactions",
    response_model=InternalTransactionListResponse,
    summary="List user transactions",
)
async def list_user_transactions(
    uid: str = Path(min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalTransactionListResponse:
    user = await _get_user_or_404(db, uid)
    result = await BalanceService.list_transactions(
        db,
        user_id=int(user.id),
        params=ListParams(page=page, page_size=page_size, order_by="created_at"),
    )
    return InternalTransactionListResponse(
        items=[InternalTransactionItem.model_validate(tx) for tx in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/users/{uid}/api-keys", summary="List user API keys")
async def list_user_api_keys(
    uid: str = Path(min_length=1),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalApiKeyItem]:
    user = await _get_user_or_404(db, uid)
    keys = await ApiKeyService.list(db, user_id=int(user.id))
    return [InternalApiKeyItem.model_validate(k) for k in keys]


@router.post("/users/{uid}/api-keys/{key_id}/disable", summary="Disable user API key")
async def disable_user_api_key(
    uid: str = Path(min_length=1),
    key_id: int = Path(gt=0),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    await ApiKeyService.disable(db, key_id=key_id, user_id=int(user.id))
    return {"uid": user.uid, "key_id": key_id, "success": True}


@router.get(
    "/usage/logs",
    response_model=InternalUsageLogListResponse,
    summary="List usage logs",
)
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    model_name: str | None = None,
    request_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUsageLogListResponse:
    params = ListParams(page=page, page_size=page_size, order_by="created_at")
    if start or end:
        params.time_field = "created_at"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    result = await UsageStatService.list_usage_logs(
        db, params=params, user_id=user_id, model_name=model_name, request_id=request_id,
    )
    return InternalUsageLogListResponse(
        items=[InternalUsageLogItem.model_validate(log) for log in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/usage/stats", summary="List usage stats")
async def list_usage_stats(
    user_id: int | None = None,
    model_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalUsageStatItem]:
    params = ListParams(page=1, page_size=1000, order_by="stat_hour")
    if start or end:
        params.time_field = "stat_hour"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    items = await UsageStatService.get_all_stats(
        db, start=params.start, end=params.end, user_id=user_id, model_name=model_name,
    )
    return [InternalUsageStatItem.model_validate(s) for s in items]


# ---------------------------------------------------------------------------
# Call-log write endpoints (router-service only)
# ---------------------------------------------------------------------------


class InternalCreateCallLogRequest(BaseModel):
    request_id: str = Field(max_length=64)
    user_id: int
    api_key_id: int | None = None
    model_name: str = Field(max_length=64)
    selected_model: str | None = Field(None, max_length=64)
    provider_slug: str | None = Field(None, max_length=32)
    upstream_model: str | None = Field(None, max_length=64)
    is_stream: bool = False
    ip: str | None = Field(None, max_length=45)
    config_version: int | None = None
    config_source: str | None = Field(None, max_length=32)
    inference_config_version: int | None = None
    inference_config_source: str | None = Field(None, max_length=32)
    routing_tier: int | None = None
    score_source: str | None = Field(None, max_length=32)
    router_trace_id: str | None = Field(None, max_length=64)
    inference_error_code: str | None = Field(None, max_length=32)
    status: int = 0


class InternalUpdateCallLogRequest(BaseModel):
    status: int | None = None
    selected_model: str | None = Field(None, max_length=64)
    provider_slug: str | None = Field(None, max_length=32)
    upstream_model: str | None = Field(None, max_length=64)
    config_version: int | None = None
    config_source: str | None = Field(None, max_length=32)
    inference_config_version: int | None = None
    inference_config_source: str | None = Field(None, max_length=32)
    routing_tier: int | None = None
    score_source: str | None = Field(None, max_length=32)
    router_trace_id: str | None = Field(None, max_length=64)
    inference_error_code: str | None = Field(None, max_length=32)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    error_code: str | None = Field(None, max_length=32)
    error_msg: str | None = Field(None, max_length=1024)
    cost: int | None = None
    provider_cost: int | None = None
    cost_detail: dict | None = None


_CALL_LOG_UPDATE_FIELDS = {
    "status", "selected_model", "provider_slug", "upstream_model",
    "config_version", "config_source", "inference_config_version",
    "inference_config_source", "routing_tier", "score_source",
    "router_trace_id", "inference_error_code", "prompt_tokens",
    "completion_tokens", "cached_tokens", "total_tokens", "duration_ms",
    "error_code", "error_msg", "cost", "provider_cost", "cost_detail",
}


@router.post("/call-logs", summary="Create API call log")
async def create_call_log(
    body: InternalCreateCallLogRequest,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    existing = (
        await db.execute(
            select(ApiCallLog).where(ApiCallLog.request_id == body.request_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": int(existing.id), "request_id": existing.request_id}

    log = ApiCallLog(
        request_id=body.request_id,
        user_id=body.user_id,
        api_key_id=body.api_key_id,
        model_name=body.model_name,
        selected_model=body.selected_model,
        provider_slug=body.provider_slug,
        upstream_model=body.upstream_model,
        is_stream=body.is_stream,
        ip=body.ip,
        config_version=body.config_version,
        config_source=body.config_source,
        inference_config_version=body.inference_config_version,
        inference_config_source=body.inference_config_source,
        routing_tier=body.routing_tier,
        score_source=body.score_source,
        router_trace_id=body.router_trace_id,
        inference_error_code=body.inference_error_code,
        status=body.status,
        created_at=now(),
        updated_at=now(),
    )
    db.add(log)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(ApiCallLog).where(ApiCallLog.request_id == body.request_id)
            )
        ).scalar_one()
        return {"id": int(existing.id), "request_id": existing.request_id}
    await db.refresh(log)
    return {"id": int(log.id), "request_id": log.request_id}


@router.patch("/call-logs/{request_id}", summary="Update API call log")
async def update_call_log(
    request_id: str = Path(max_length=64),
    body: InternalUpdateCallLogRequest = ...,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    log = (
        await db.execute(
            select(ApiCallLog).where(ApiCallLog.request_id == request_id)
        )
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="call log not found")

    updates = body.model_dump(exclude_unset=True)
    if "error_msg" in updates and updates["error_msg"] is not None:
        updates["error_msg"] = updates["error_msg"][:512]

    for field_name, value in updates.items():
        if field_name in _CALL_LOG_UPDATE_FIELDS:
            setattr(log, field_name, value)
    log.updated_at = now()
    await db.commit()

    cost = updates.get("cost", 0) or 0
    final_status = updates.get("status")
    if cost > 0 and final_status == 1:
        tx_repo = BalanceTxRepository(db)
        already_billed = await tx_repo.exists_by_ref(
            tx_type=BalanceTransaction.TYPE_CONSUME,
            ref_type="api_call",
            ref_id=request_id,
        )
        if not already_billed:
            user = await UserRepository(db).get_by_id(log.user_id, for_update=True)
            if user is not None:
                balance_before = int(user.balance)
                user.balance = max(int(user.balance) - cost, 0)
                user.used_amount += cost
                user.total_requests += 1
                total_tokens = updates.get("total_tokens", 0) or 0
                user.total_tokens += total_tokens
                tx_repo.add(
                    BalanceTransaction(
                        user_id=user.id,
                        type=BalanceTransaction.TYPE_CONSUME,
                        amount=-cost,
                        balance_before=balance_before,
                        balance_after=int(user.balance),
                        ref_type="api_call",
                        ref_id=request_id,
                    )
                )
                if log.api_key_id:
                    api_key = await ApiKeyRepository(db).get_owned_key(
                        log.api_key_id, user.id, for_update=True,
                    )
                    if api_key is not None:
                        api_key.quota_used += cost
                await db.commit()

    return {"ok": True}


class InternalBatchCallLogRequest(BaseModel):
    entries: list[dict] = Field(max_length=500)


_CREATE_FIELDS = {
    "request_id", "user_id", "api_key_id", "model_name", "selected_model",
    "provider_slug", "upstream_model", "is_stream", "ip", "config_version",
    "config_source", "inference_config_version", "inference_config_source",
    "routing_tier", "score_source", "router_trace_id", "inference_error_code",
    "status",
}


@router.post("/call-logs/batch", summary="Batch create/update call logs")
async def batch_call_logs(
    body: InternalBatchCallLogRequest,
    _: None = Depends(verify_router_only),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    created = 0
    updated = 0
    billed = 0

    for entry in body.entries:
        request_id = entry.get("request_id")
        if not request_id:
            continue
        action = entry.get("action", "create")

        existing = (
            await db.execute(
                select(ApiCallLog).where(ApiCallLog.request_id == request_id)
            )
        ).scalar_one_or_none()

        if existing is None:
            create_fields = {k: v for k, v in entry.items() if k in _CREATE_FIELDS and v is not None}
            if "request_id" not in create_fields:
                create_fields["request_id"] = request_id
            log = ApiCallLog(**create_fields, created_at=now(), updated_at=now())
            db.add(log)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                existing = (
                    await db.execute(
                        select(ApiCallLog).where(ApiCallLog.request_id == request_id)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    continue
            else:
                created += 1
                if action != "complete":
                    continue
                existing = log

        update_fields = {k: v for k, v in entry.items() if k in _CALL_LOG_UPDATE_FIELDS and v is not None}
        if "error_msg" in update_fields and update_fields["error_msg"] is not None:
            update_fields["error_msg"] = str(update_fields["error_msg"])[:512]
        for field_name, value in update_fields.items():
            setattr(existing, field_name, value)
        existing.updated_at = now()
        updated += 1

        if action == "complete":
            cost = entry.get("cost", 0) or 0
            final_status = entry.get("status")
            if cost > 0 and final_status == 1:
                tx_repo = BalanceTxRepository(db)
                already_billed = await tx_repo.exists_by_ref(
                    tx_type=BalanceTransaction.TYPE_CONSUME,
                    ref_type="api_call",
                    ref_id=request_id,
                )
                if not already_billed:
                    user = await UserRepository(db).get_by_id(existing.user_id, for_update=True)
                    if user is not None:
                        balance_before = int(user.balance)
                        user.balance = max(int(user.balance) - cost, 0)
                        user.used_amount += cost
                        user.total_requests += 1
                        total_tokens = entry.get("total_tokens", 0) or 0
                        user.total_tokens += total_tokens
                        tx_repo.add(
                            BalanceTransaction(
                                user_id=user.id,
                                type=BalanceTransaction.TYPE_CONSUME,
                                amount=-cost,
                                balance_before=balance_before,
                                balance_after=int(user.balance),
                                ref_type="api_call",
                                ref_id=request_id,
                            )
                        )
                        if existing.api_key_id:
                            api_key = await ApiKeyRepository(db).get_owned_key(
                                existing.api_key_id, user.id, for_update=True,
                            )
                            if api_key is not None:
                                api_key.quota_used += cost
                        await db.flush()
                        billed += 1

    await db.commit()
    return {"ok": True, "created": created, "updated": updated, "billed": billed}
