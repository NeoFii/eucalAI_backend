"""Admin-facing voucher management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session
from admin_service.gateway import UserManagementGateway
from admin_service.models import AdminUser
from admin_service.policies import require_active_admin, require_super_admin
from admin_service.schemas.voucher import (
    CreateVoucherRequest,
    UpdateVoucherRequest,
    VoucherItem,
    VoucherListResponse,
    VoucherOperationResponse,
    VoucherResponse,
)
from admin_service.services.audit_service import AdminAuditService
from common.api import PaginatedResponse

router = APIRouter(prefix="/vouchers", tags=["voucher-management"])
_gateway = UserManagementGateway()


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


@router.post("", response_model=VoucherResponse, summary="Create user voucher")
async def create_user_voucher(
    payload: CreateVoucherRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherResponse:
    data = await _gateway.create_voucher(
        uid=payload.uid,
        amount=payload.amount,
        expires_at=payload.expires_at,
        operator_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = _request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="create_voucher",
        resource_type="voucher",
        resource_id=str(data["id"]),
        status="success",
        after_data={"uid": payload.uid, "amount": payload.amount, "remark": payload.remark},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return VoucherResponse(data=VoucherItem(**data))


@router.get("", response_model=VoucherListResponse, summary="List user vouchers")
async def list_user_vouchers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    status: int | None = None,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> VoucherListResponse:
    data = await _gateway.list_vouchers(
        page=page,
        page_size=page_size,
        user_id=user_id,
        status=status,
    )
    return VoucherListResponse(
        data=PaginatedResponse[VoucherItem](
            items=[VoucherItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        )
    )


@router.get("/{voucher_id}", response_model=VoucherResponse, summary="Get voucher")
async def get_user_voucher(
    voucher_id: int,
    _current_admin: AdminUser = Depends(require_active_admin),
) -> VoucherResponse:
    data = await _gateway.get_voucher(voucher_id)
    return VoucherResponse(data=VoucherItem(**data))


@router.patch("/{voucher_id}", response_model=VoucherResponse, summary="Update voucher")
async def update_user_voucher(
    voucher_id: int,
    payload: UpdateVoucherRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherResponse:
    data = await _gateway.update_voucher(
        voucher_id,
        status=payload.status,
        expires_at=payload.expires_at,
        operator_uid=current_admin.uid,
        remark=payload.remark,
    )
    ip_address, user_agent = _request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="update_voucher",
        resource_type="voucher",
        resource_id=str(voucher_id),
        status="success",
        after_data=payload.model_dump(exclude_unset=True),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return VoucherResponse(data=VoucherItem(**data))


@router.delete("/{voucher_id}", response_model=VoucherOperationResponse, summary="Delete voucher")
async def delete_user_voucher(
    voucher_id: int,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherOperationResponse:
    await _gateway.delete_voucher(voucher_id, operator_uid=current_admin.uid)
    ip_address, user_agent = _request_meta(request)
    await AdminAuditService.record(
        db,
        actor_admin_id=current_admin.id,
        target_admin_id=None,
        action="delete_voucher",
        resource_type="voucher",
        resource_id=str(voucher_id),
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return VoucherOperationResponse(message="删除成功")
