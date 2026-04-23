"""Invitation-code admin endpoints."""

import logging

from fastapi import APIRouter, Depends, Query, Request
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
    InvitationCodeOperationResponse,
    UpdateInvitationCodeRequest,
)
from admin_service.services.invitation_service import InvitationCodeService
from common.api import PaginatedResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["invitation-codes"])
_stats_gateway = UserStatsGateway()


@router.get(
    "/dashboard/stats", response_model=DashboardStatsResponse, summary="Get dashboard stats"
)
async def get_dashboard_stats(
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardStatsResponse:
    code_stats = await InvitationCodeService.get_stats(db)
    total_users = await _stats_gateway.fetch_total_users()
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
    payload: GenerateInvitationCodeRequest,
    http_request: Request,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> GenerateInvitationCodeResponse:
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("user-agent")
    codes = await InvitationCodeService.generate(
        db=db,
        created_by=current_admin.id,
        quantity=payload.quantity,
        expires_days=payload.expires_days,
        expires_at=payload.expires_at,
        max_uses=payload.max_uses,
        remark=payload.remark,
        actor_admin_id=current_admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
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
    status: int | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeListResponse:
    codes, total = await InvitationCodeService.list(
        db=db, page=page, page_size=page_size, status=status
    )
    return InvitationCodeListResponse(
        code=200,
        message="success",
        data=PaginatedResponse[InvitationCodeListItem](
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
    http_request: Request,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("user-agent")
    await InvitationCodeService.enable(
        db, code_id,
        actor_admin_id=current_admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return InvitationCodeOperationResponse(code=200, message="success")


@router.patch(
    "/invitation-codes/{code_id}/disable",
    response_model=InvitationCodeOperationResponse,
    summary="Disable invitation code",
)
async def disable_invitation_code(
    code_id: int,
    http_request: Request,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("user-agent")
    await InvitationCodeService.disable(
        db, code_id,
        actor_admin_id=current_admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return InvitationCodeOperationResponse(code=200, message="success")


@router.patch(
    "/invitation-codes/{code_id}",
    response_model=InvitationCodeOperationResponse,
    summary="Update invitation code",
)
async def update_invitation_code(
    code_id: int,
    payload: UpdateInvitationCodeRequest,
    http_request: Request,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("user-agent")
    await InvitationCodeService.update(
        db,
        code_id,
        expires_at=payload.expires_at,
        remark=payload.remark,
        actor_admin_id=current_admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return InvitationCodeOperationResponse(code=200, message="success")
