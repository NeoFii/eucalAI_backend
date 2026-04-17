# -*- coding: utf-8 -*-
"""
Testing 服务模型报价管理端点
提供模型-服务商报价配置的软删除操作
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_service.api.dependencies import AdminPrincipal, get_current_admin, get_db_session
from testing_service.schemas import ApiResponse
from testing_service.provider_config import OfferingService

router = APIRouter(prefix="/model-providers", tags=["模型报价管理"])


@router.delete(
    "/{offering_id}",
    response_model=ApiResponse[None],
    summary="软删除模型服务商报价",
    description="将指定报价配置的 is_active 设置为 False（软删除，不物理删除）",
)
async def delete_model_offering(
    offering_id: int,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """软删除报价配置"""
    found = await OfferingService.delete(db, offering_id)
    if not found:
        return {"code": 404, "message": "报价配置不存在", "data": None}
    return {"code": 200, "message": "已废弃", "data": None}
