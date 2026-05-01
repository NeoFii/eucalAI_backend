"""Internal user management endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.utils.password import hash_password
from controllers.internal import verify_internal_secret
from core.dependencies import get_db_session
from repositories.user_repository import UserRepository
from schemas.internal_user_mgmt import (
    InternalAdjustBalanceRequest,
    InternalApiKeyItem,
    InternalResetPasswordRequest,
    InternalTopupRequest,
    InternalTransactionItem,
    InternalTransactionListResponse,
    InternalUpdateStatusRequest,
    InternalUpdateStatusResponse,
    InternalUserDetailResponse,
    InternalUserListItem,
    InternalUserListResponse,
)
from services.api_key_service import ApiKeyService
from services.auth_service import AuthService
from services.balance_service import BalanceService
from services.topup_order_service import TopupOrderService

logger = logging.getLogger("user_service.internal.user_mgmt")

router = APIRouter(prefix="/internal", tags=["internal"])


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
    from utils.password import check_password_strength

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
