"""Admin-facing voucher management endpoints — proxy elimination.

Ported from services/admin-service/src/controllers/vouchers.py.
All gateway calls replaced with AdminVoucherService direct calls.
All safe_audit_commit replaced with inline AdminAuditService.record + db.commit().
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.schemas import BaseResponse
from api_service.common.utils.timezone import format_iso
from api_service.core.db import get_db
from api_service.core.dependencies.admin import get_request_meta
from api_service.core.policies import require_active_admin, require_super_admin
from api_service.models import AdminUser
from api_service.schemas.admin.voucher import (
    GenerateVoucherCodesRequest,
    VoucherCodeCreateData,
    VoucherCodeCreateResponse,
    VoucherCodeItem,
    VoucherCodeListResponse,
    VoucherCodeResponse,
    VoucherOperationResponse,
    CreatedVoucherCodeItem,
)
from api_service.services.admin.audit_service import AdminAuditService
from api_service.services.admin.voucher_service import AdminVoucherService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vouchers", tags=["admin-vouchers"])


@router.post("", response_model=VoucherCodeCreateResponse, summary="Generate voucher codes")
async def generate_voucher_codes(
    payload: GenerateVoucherCodesRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> VoucherCodeCreateResponse:
    codes = await AdminVoucherService.generate_codes(
        db,
        amount=payload.amount,
        count=payload.count,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        operator_admin_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="generate_voucher_codes",
        resource_type="voucher_redemption_code",
        resource_id="batch",
        status="success",
        after_data={
            "amount": payload.amount,
            "count": payload.count,
            "starts_at": format_iso(payload.starts_at),
            "expires_at": format_iso(payload.expires_at),
            "remark": payload.remark,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return VoucherCodeCreateResponse(
        data=VoucherCodeCreateData(
            items=[
                CreatedVoucherCodeItem(
                    id=getattr(c.record, "id", 0) if hasattr(c, "record") else 0,
                    code=c.code,
                    code_prefix=c.code[:4] if hasattr(c, "code") else "",
                    code_suffix=c.code[-4:] if hasattr(c, "code") else "",
                    amount=payload.amount,
                    status=1,
                    starts_at=payload.starts_at,
                    expires_at=payload.expires_at,
                    created_by_admin_uid=current_admin.uid,
                    remark=payload.remark,
                )
                for c in codes
            ]
        )
    )


@router.get("", response_model=VoucherCodeListResponse, summary="List voucher codes")
async def list_voucher_codes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: int | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> VoucherCodeListResponse:
    items, total = await AdminVoucherService.list_codes(
        db, page=page, page_size=page_size, status=status,
    )
    return VoucherCodeListResponse(
        data={
            "items": [
                VoucherCodeItem.model_validate(v, from_attributes=True).model_dump(mode="json")
                for v in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/{code_id}", response_model=VoucherCodeResponse, summary="Get voucher code")
async def get_voucher_code(
    code_id: int,
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> VoucherCodeResponse:
    code = await AdminVoucherService.get(db, code_id=code_id)
    return VoucherCodeResponse(data=VoucherCodeItem.model_validate(code, from_attributes=True))


@router.delete(
    "/{code_id}",
    response_model=VoucherOperationResponse,
    summary="Disable voucher code",
)
async def disable_voucher_code(
    code_id: int,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> VoucherOperationResponse:
    await AdminVoucherService.disable(db, code_id=code_id, operator_uid=current_admin.uid)
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="disable_voucher_code",
        resource_type="voucher_redemption_code",
        resource_id=str(code_id),
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return VoucherOperationResponse(message="禁用成功")
