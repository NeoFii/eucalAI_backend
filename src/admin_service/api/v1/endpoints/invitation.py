"""Invitation-code admin endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session
from admin_service.gateway import UserStatsGateway
from admin_service.models import AdminUser
from admin_service.policies import require_active_admin
from admin_service.schemas import (
    DashboardStatsResponse,
    DashboardStatsResponseData,
    GenerateInvitationCodeRequest,
    GenerateInvitationCodeResponse,
    GenerateInvitationCodeResponseData,
    InvitationCodeData,
    InvitationCodeListItem,
    InvitationCodeListResponse,
    InvitationCodeListResponseData,
    InvitationCodeOperationResponse,
    UpdateInvitationCodeRequest,
)
from admin_service.services.invitation_service import InvitationCodeService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["invitation-codes"])


@router.get(
    "/dashboard/stats", response_model=DashboardStatsResponse, summary="Get dashboard stats"
)
async def get_dashboard_stats(
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardStatsResponse:
    del current_admin
    code_stats = await InvitationCodeService.get_stats(db)
    total_users = await UserStatsGateway().fetch_total_users()
    return DashboardStatsResponse(
        code=200,
        message="success",
        data=DashboardStatsResponseData(
            total_users=total_users,
            total_invitation_codes=code_stats["total"],
            used_invitation_codes=code_stats["used"],
            valid_invitation_codes=code_stats["valid"],
        ),
    )


@router.post(
    "/invitation-codes/generate",
    response_model=GenerateInvitationCodeResponse,
    summary="Generate invitation codes",
)
async def generate_invitation_codes(
    request: GenerateInvitationCodeRequest,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> GenerateInvitationCodeResponse:
    codes = await InvitationCodeService.generate(
        db=db,
        created_by=current_admin.id,
        quantity=request.quantity,
        expires_days=request.expires_days,
        expires_at=request.expires_at,
        max_uses=request.max_uses,
        remark=request.remark,
    )
    return GenerateInvitationCodeResponse(
        code=200,
        message="success",
        data=GenerateInvitationCodeResponseData(
            codes=[
                InvitationCodeData(
                    id=code.id,
                    code=code.code,
                    status=code.status,
                    expires_at=code.expires_at,
                    used_by=code.used_by,
                    used_at=code.used_at,
                    remark=code.remark,
                    created_at=code.created_at,
                )
                for code in codes
            ]
        ),
    )


@router.get(
    "/invitation-codes", response_model=InvitationCodeListResponse, summary="List invitation codes"
)
async def list_invitation_codes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[int] = Query(None),
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeListResponse:
    del current_admin
    codes, total = await InvitationCodeService.list(
        db=db, page=page, page_size=page_size, status=status
    )
    return InvitationCodeListResponse(
        code=200,
        message="success",
        data=InvitationCodeListResponseData(
            items=[
                InvitationCodeListItem(
                    id=code.id,
                    code=code.code,
                    status=code.status,
                    created_by=code.created_by,
                    used_by=code.used_by,
                    used_at=code.used_at,
                    expires_at=code.expires_at,
                    remark=code.remark,
                    created_at=code.created_at,
                )
                for code in codes
            ],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.patch(
    "/invitation-codes/{code_id}/enable",
    response_model=InvitationCodeOperationResponse,
    summary="Enable invitation code",
)
async def enable_invitation_code(
    code_id: int,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    del current_admin
    await InvitationCodeService.enable(db, code_id)
    return InvitationCodeOperationResponse(code=200, message="success")


@router.patch(
    "/invitation-codes/{code_id}/disable",
    response_model=InvitationCodeOperationResponse,
    summary="Disable invitation code",
)
async def disable_invitation_code(
    code_id: int,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    del current_admin
    await InvitationCodeService.disable(db, code_id)
    return InvitationCodeOperationResponse(code=200, message="success")


@router.patch(
    "/invitation-codes/{code_id}",
    response_model=InvitationCodeOperationResponse,
    summary="Update invitation code",
)
async def update_invitation_code(
    code_id: int,
    request: UpdateInvitationCodeRequest,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    del current_admin
    await InvitationCodeService.update(
        db,
        code_id,
        expires_at=request.expires_at,
        remark=request.remark,
    )
    return InvitationCodeOperationResponse(code=200, message="success")
