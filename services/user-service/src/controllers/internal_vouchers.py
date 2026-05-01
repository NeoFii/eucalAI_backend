"""Internal voucher management endpoints."""

import logging

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from controllers.internal import verify_internal_secret
from core.dependencies import get_db_session
from schemas.internal_vouchers import (
    InternalCreatedVoucherItem,
    InternalVoucherCreateResponse,
    InternalVoucherDisableRequest,
    InternalVoucherGenerateRequest,
    InternalVoucherItem,
    InternalVoucherListResponse,
)
from services.voucher_service import VoucherService

logger = logging.getLogger("user_service.internal.vouchers")

router = APIRouter(prefix="/internal", tags=["internal"])


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
