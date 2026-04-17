# -*- coding: utf-8 -*-
"""
Testing 服务研发商端点
提供研发商的查询与管理接口（研发商 = 创造模型的公司，如 Anthropic / OpenAI / DeepSeek）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing_service.dependencies import AdminPrincipal, get_current_admin, get_db_session
from testing_service.schemas import (
    ApiResponse,
    ListResponse,
    ModelVendorResponse,
    VendorCreate,
    VendorUpdate,
)
from testing_service.catalog import VendorService

router = APIRouter(prefix="/vendors", tags=["研发商"])


@router.get(
    "",
    response_model=ApiResponse[ListResponse[ModelVendorResponse]],
    summary="获取研发商列表",
    description="获取所有研发商（含已停用），按名称排序",
)
async def list_vendors(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取所有研发商，管理端展示，支持分页"""
    items_raw, total = await VendorService.list_all(db, page, page_size)
    items = [ModelVendorResponse.model_validate(v) for v in items_raw]
    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.post(
    "",
    response_model=ApiResponse[ModelVendorResponse],
    status_code=201,
    summary="创建研发商",
)
async def create_vendor(
    data: VendorCreate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建新研发商（slug 唯一；软删除记录自动恢复）"""
    try:
        vendor = await VendorService.create(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "code": 201,
        "message": "created",
        "data": ModelVendorResponse.model_validate(vendor),
    }


@router.put(
    "/{vendor_id}",
    response_model=ApiResponse[ModelVendorResponse],
    summary="更新研发商",
)
async def update_vendor(
    vendor_id: int,
    data: VendorUpdate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """更新研发商信息"""
    vendor = await VendorService.update(db, vendor_id, data)
    if not vendor:
        raise HTTPException(status_code=404, detail="研发商不存在")
    return {
        "code": 200,
        "message": "success",
        "data": ModelVendorResponse.model_validate(vendor),
    }


@router.delete(
    "/{vendor_id}",
    response_model=ApiResponse[None],
    summary="软删除研发商",
    description="将研发商设置为 is_active=False；若存在关联模型则拒绝",
)
async def delete_vendor(
    vendor_id: int,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """软删除研发商（存在关联模型时拒绝）"""
    ok, reason = await VendorService.delete(db, vendor_id)
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="研发商不存在")
        raise HTTPException(status_code=400, detail=reason)
    return {"code": 200, "message": "deleted", "data": None}
