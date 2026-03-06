"""
邀请码管理端点
提供邀请码的生成、查询、启用/禁用等接口
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from admin.dependencies import get_current_admin, get_db_session
from admin.models import AdminUser, InvitationCode
from admin.schemas import (
    DashboardStatsResponse,
    DashboardStatsResponseData,
    DisableInvitationCodeRequest,
    EnableInvitationCodeRequest,
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
from admin.services.invitation_service import InvitationCodeService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["邀请码管理"])


@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    summary="获取仪表盘统计",
    description="获取系统统计数据",
)
async def get_dashboard_stats(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardStatsResponse:
    """获取仪表盘统计数据"""
    # 统计邀请码
    code_stats = await InvitationCodeService.get_stats(db)

    # 统计用户数（从 users 表）
    from sqlalchemy import select, func
    from user.models import User

    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0

    return DashboardStatsResponse(
        code=200,
        message="获取成功",
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
    summary="生成邀请码",
    description="批量生成邀请码",
)
async def generate_invitation_codes(
    request: GenerateInvitationCodeRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> GenerateInvitationCodeResponse:
    """生成邀请码"""
    codes = await InvitationCodeService.generate(
        db=db,
        created_by=current_admin.uid,
        quantity=request.quantity,
        expires_days=request.expires_days,
        expires_at=request.expires_at,
        max_uses=request.max_uses,
        remark=request.remark,
    )

    return GenerateInvitationCodeResponse(
        code=200,
        message=f"成功生成 {len(codes)} 个邀请码",
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
    "/invitation-codes",
    response_model=InvitationCodeListResponse,
    summary="获取邀请码列表",
    description="分页获取邀请码列表",
)
async def list_invitation_codes(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[int] = Query(None, description="状态过滤：0=已弃用 1=有效 2=已使用"),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeListResponse:
    """获取邀请码列表"""
    codes, total = await InvitationCodeService.list(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
    )

    return InvitationCodeListResponse(
        code=200,
        message="获取成功",
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
    summary="启用邀请码",
    description="启用指定的邀请码",
)
async def enable_invitation_code(
    code_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    """启用邀请码"""
    await InvitationCodeService.enable(db, code_id)
    return InvitationCodeOperationResponse(code=200, message="邀请码已启用")


@router.patch(
    "/invitation-codes/{code_id}/disable",
    response_model=InvitationCodeOperationResponse,
    summary="弃用邀请码",
    description="弃用指定的邀请码",
)
async def disable_invitation_code(
    code_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    """弃用邀请码"""
    await InvitationCodeService.disable(db, code_id)
    return InvitationCodeOperationResponse(code=200, message="邀请码已弃用")


@router.patch(
    "/invitation-codes/{code_id}",
    response_model=InvitationCodeOperationResponse,
    summary="更新邀请码",
    description="更新邀请码信息（失效时间、备注等）",
)
async def update_invitation_code(
    code_id: int,
    request: UpdateInvitationCodeRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InvitationCodeOperationResponse:
    """更新邀请码"""
    await InvitationCodeService.update(
        db,
        code_id,
        expires_at=request.expires_at,
        remark=request.remark,
    )
    return InvitationCodeOperationResponse(code=200, message="邀请码已更新")
