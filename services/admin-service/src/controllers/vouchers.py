"""Admin-facing voucher redemption-code management endpoints (facade over user-service).

These endpoints proxy voucher operations to user-service via the gateway layer.
They belong to the admin control-plane facade, not the admin domain proper.
"""
# ruff: noqa: B008

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, get_request_meta
from gateways.user_management import UserManagementGateway
from models import AdminUser
from core.policies import require_active_admin, require_super_admin
from schemas.voucher import (
    CreatedVoucherCodeItem,
    GenerateVoucherCodesRequest,
    VoucherCodeCreateData,
    VoucherCodeCreateResponse,
    VoucherCodeItem,
    VoucherCodeListResponse,
    VoucherCodeResponse,
    VoucherOperationResponse,
)
from utils.audit import safe_audit_commit
from common.api import PaginatedResponse
from common.utils.timezone import format_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vouchers", tags=["voucher-management"])
_gateway = UserManagementGateway()


@router.post("", response_model=VoucherCodeCreateResponse, summary="Generate voucher codes")
async def generate_voucher_codes(
    payload: GenerateVoucherCodesRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherCodeCreateResponse:
    data = await _gateway.generate_voucher_codes(
        amount=payload.amount,
        count=payload.count,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        operator_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await safe_audit_commit(
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
    return VoucherCodeCreateResponse(
        data=VoucherCodeCreateData(
            items=[CreatedVoucherCodeItem(**item) for item in data["items"]]
        )
    )


@router.get("", response_model=VoucherCodeListResponse, summary="List voucher codes")
async def list_voucher_codes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: int | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> VoucherCodeListResponse:
    data = await _gateway.list_voucher_codes(
        page=page,
        page_size=page_size,
        status=status,
    )
    return VoucherCodeListResponse(
        data=PaginatedResponse[VoucherCodeItem](
            items=[VoucherCodeItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        )
    )


@router.get("/{code_id}", response_model=VoucherCodeResponse, summary="Get voucher code")
async def get_voucher_code(
    code_id: int,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> VoucherCodeResponse:
    data = await _gateway.get_voucher_code(code_id)
    return VoucherCodeResponse(data=VoucherCodeItem(**data))


@router.delete(
    "/{code_id}",
    response_model=VoucherOperationResponse,
    summary="Disable voucher code",
)
async def disable_voucher_code(
    code_id: int,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherOperationResponse:
    await _gateway.disable_voucher_code(code_id, operator_uid=current_admin.uid)
    ip_address, user_agent = get_request_meta(request)
    await safe_audit_commit(
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
    return VoucherOperationResponse(message="禁用成功")
