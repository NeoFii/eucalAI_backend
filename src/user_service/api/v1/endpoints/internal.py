"""Internal user-service endpoints."""

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.internal import build_internal_auth_dependency
from common.utils import hash_password
from common.utils.timezone import now
from user_service.config import settings
from user_service.dependencies import get_db_session
from user_service.repositories.user_repository import UserRepository
from user_service.services.api_key_service import ApiKeyService
from user_service.services.auth_service import AuthService
from user_service.services.balance_service import BalanceService
from user_service.services.topup_order_service import TopupOrderService
from user_service.services.usage_stat_service import UsageStatService
from user_service.services.voucher_service import VoucherService

router = APIRouter(prefix="/internal", tags=["internal"])
verify_internal_secret = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"admin-service", "router-service"},
)


class InternalUserResponse(BaseModel):
    id: int
    uid: int
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


# --- Admin user-management schemas ---


class InternalUserListItem(BaseModel):
    uid: int
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
    uid: int
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
    status: int


class InternalUpdateStatusResponse(BaseModel):
    uid: int
    before_status: int
    after_status: int


class InternalResetPasswordRequest(BaseModel):
    new_password: str


class InternalTopupRequest(BaseModel):
    amount: int
    operator_uid: int  # admin snowflake uid, stored as operator_id in DB
    remark: str = ""


class InternalAdjustBalanceRequest(BaseModel):
    amount: int
    operator_uid: int  # admin snowflake uid, stored as operator_id in DB
    remark: str


class InternalTransactionItem(BaseModel):
    id: int
    type: int
    amount: int
    balance_before: int
    balance_after: int
    ref_type: str | None = None
    ref_id: str | None = None
    remark: str | None = None
    operator_id: int | None = None
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
    amount: int
    count: int
    starts_at: datetime
    expires_at: datetime
    operator_uid: int | None = None
    remark: str | None = None


class InternalVoucherDisableRequest(BaseModel):
    operator_uid: int | None = None


class InternalVoucherItem(BaseModel):
    id: int
    code_prefix: str
    code_suffix: str
    amount: int
    status: int
    starts_at: datetime
    expires_at: datetime
    redeemed_user_id: int | None = None
    redeemed_at: datetime | None = None
    created_by_admin_uid: int | None = None
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
    uid: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserResponse:
    user = await UserRepository(db).get_by_uid(uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return InternalUserResponse(
        id=int(user.id),
        uid=int(user.uid),
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
    return InternalApiKeyValidateResponse(
        id=int(api_key.id),
        user_id=int(api_key.user_id),
        name=api_key.name,
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
    voucher_id: int,
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
    voucher_id: int,
    payload: InternalVoucherDisableRequest,
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


async def _get_user_or_404(db: AsyncSession, uid: int):
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
    uid: int,
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
    uid: int,
    payload: InternalUpdateStatusRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUpdateStatusResponse:
    if payload.status not in (0, 1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 0 or 1",
        )
    user = await _get_user_or_404(db, uid)
    before_status = int(user.status)
    user.status = payload.status
    await db.commit()
    return InternalUpdateStatusResponse(
        uid=int(user.uid), before_status=before_status, after_status=payload.status,
    )


@router.post("/users/{uid}/reset-password", summary="Reset user password")
async def reset_user_password(
    uid: int,
    payload: InternalResetPasswordRequest,
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
    return {"uid": int(user.uid), "success": True}


@router.post("/users/{uid}/topup", summary="Manual topup")
async def topup_user(
    uid: int,
    payload: InternalTopupRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    # operator_uid is admin's snowflake uid, passed through as operator_id
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
    uid: int,
    payload: InternalAdjustBalanceRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    # operator_uid is admin's snowflake uid, passed through as operator_id
    await BalanceService.admin_adjust(
        db,
        user_id=int(user.id),
        amount=payload.amount,
        operator_id=payload.operator_uid,
        remark=payload.remark,
    )
    return {"uid": int(user.uid), "success": True}


@router.get(
    "/users/{uid}/transactions",
    response_model=InternalTransactionListResponse,
    summary="List user transactions",
)
async def list_user_transactions(
    uid: int,
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
    uid: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalApiKeyItem]:
    user = await _get_user_or_404(db, uid)
    keys = await ApiKeyService.list(db, user_id=int(user.id))
    return [InternalApiKeyItem.model_validate(k) for k in keys]


@router.post("/users/{uid}/api-keys/{key_id}/disable", summary="Disable user API key")
async def disable_user_api_key(
    uid: int,
    key_id: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await _get_user_or_404(db, uid)
    await ApiKeyService.disable(db, key_id=key_id, user_id=int(user.id))
    return {"uid": int(user.uid), "key_id": key_id, "success": True}


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
        db, params=params, user_id=user_id, model_name=model_name,
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
