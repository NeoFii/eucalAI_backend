"""
邀请码管理 API 端点
提供邀请码的生成、查询、启用/弃用等功能
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.invitation_schemas import (
    DisableInvitationCodeResponse,
    EnableInvitationCodeResponse,
    GenerateInvitationCodesRequest,
    GenerateInvitationCodesResponse,
    GenerateInvitationCodesResponseData,
    GetInvitationCodeListResponse,
    GetInvitationCodeListResponseData,
    InvitationCodeData,
)
from app.services.invitation_service import invitation_service

router = APIRouter(tags=["邀请码管理"])


@router.post(
    "/admin/invitation-codes",
    response_model=GenerateInvitationCodesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="批量生成邀请码",
)
async def generate_invitation_codes(
    request: GenerateInvitationCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateInvitationCodesResponse:
    """
    批量生成邀请码

    - 使用 secrets.token_urlsafe(16) 生成高熵随机字符串（22位，128bit熵）
    - 生成的邀请码仅在此处返回一次明文，请妥善保存

    - **count**: 生成数量（1-100）
    - **expires_at**: 过期时间（可选，ISO 8601格式）
    - **remark**: 管理备注（可选）
    """
    # TODO: 添加管理员权限校验
    codes = await invitation_service.generate_codes(
        db=db,
        count=request.count,
        created_by=None,  # TODO: 从当前登录用户获取
        expires_at=request.expires_at,
        remark=request.remark,
    )

    # 提交事务
    await db.commit()

    return GenerateInvitationCodesResponse(
        code=201,
        message="生成成功",
        data=GenerateInvitationCodesResponseData(
            codes=[
                InvitationCodeData(
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
            total=len(codes),
        ),
    )


@router.get(
    "/admin/invitation-codes",
    response_model=GetInvitationCodeListResponse,
    summary="分页查询邀请码列表",
)
async def get_invitation_code_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status: Optional[int] = Query(default=None, ge=0, le=2, description="状态过滤：0=未使用, 1=已使用, 2=已弃用"),
    db: AsyncSession = Depends(get_db),
) -> GetInvitationCodeListResponse:
    """
    分页查询邀请码列表

    - 支持按状态过滤
    - 按创建时间倒序排列

    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（1-100）
    - **status**: 状态过滤（可选）
    """
    # TODO: 添加管理员权限校验
    codes, total = await invitation_service.get_code_list(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
    )

    return GetInvitationCodeListResponse(
        code=200,
        message="查询成功",
        data=GetInvitationCodeListResponseData(
            items=[
                InvitationCodeData(
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
    "/admin/invitation-codes/{code_id}/disable",
    response_model=DisableInvitationCodeResponse,
    summary="弃用邀请码",
)
async def disable_invitation_code(
    code_id: int,
    db: AsyncSession = Depends(get_db),
) -> DisableInvitationCodeResponse:
    """
    弃用邀请码

    - 将邀请码状态设为 2（已弃用）
    - 已使用的邀请码不能弃用

    - **code_id**: 邀请码 ID
    """
    # TODO: 添加管理员权限校验
    code = await invitation_service.disable_code(db, code_id)
    await db.commit()

    return DisableInvitationCodeResponse(
        code=200,
        message="弃用成功",
        data=InvitationCodeData(
            id=code.id,
            code=code.code,
            status=code.status,
            created_by=code.created_by,
            used_by=code.used_by,
            used_at=code.used_at,
            expires_at=code.expires_at,
            remark=code.remark,
            created_at=code.created_at,
        ),
    )


@router.patch(
    "/admin/invitation-codes/{code_id}/enable",
    response_model=EnableInvitationCodeResponse,
    summary="启用/恢复邀请码",
)
async def enable_invitation_code(
    code_id: int,
    db: AsyncSession = Depends(get_db),
) -> EnableInvitationCodeResponse:
    """
    启用/恢复邀请码

    - 将已弃用的邀请码状态重置为 0（未使用）
    - 已使用的邀请码不能恢复

    - **code_id**: 邀请码 ID
    """
    # TODO: 添加管理员权限校验
    code = await invitation_service.enable_code(db, code_id)
    await db.commit()

    return EnableInvitationCodeResponse(
        code=200,
        message="启用成功",
        data=InvitationCodeData(
            id=code.id,
            code=code.code,
            status=code.status,
            created_by=code.created_by,
            used_by=code.used_by,
            used_at=code.used_at,
            expires_at=code.expires_at,
            remark=code.remark,
            created_at=code.created_at,
        ),
    )
