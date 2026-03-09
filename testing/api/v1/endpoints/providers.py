# -*- coding: utf-8 -*-
"""
Testing 服务提供商端点
提供 API 服务提供商的查询与管理接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.schemas import ApiResponse, ListResponse, ProviderResponse, ProviderCreate, ProviderUpdate
from testing.services import ProviderService

router = APIRouter(prefix="/providers", tags=["服务提供商"])


@router.get(
    "",
    response_model=ApiResponse[ListResponse[ProviderResponse]],
    summary="获取服务提供商列表",
    description="获取所有启用的 API 服务提供商，按名称排序",
)
async def list_providers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取所有服务提供商列表，支持分页"""
    items_raw, total = await ProviderService.list_all(db, page, page_size)
    items = [ProviderResponse.model_validate(p) for p in items_raw]
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get(
    "/{slug}",
    response_model=ApiResponse[ProviderResponse],
    summary="获取服务提供商详情",
    description="根据 slug 获取服务提供商详情",
)
async def get_provider(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """根据 slug 获取服务提供商详情"""
    provider = await ProviderService.get_by_slug(db, slug)
    if not provider:
        raise HTTPException(status_code=404, detail="提供商不存在")
    return {
        "code": 200,
        "message": "success",
        "data": ProviderResponse.model_validate(provider),
    }


@router.post(
    "",
    response_model=ApiResponse[ProviderResponse],
    status_code=201,
    summary="创建服务提供商",
)
async def create_provider(
    data: ProviderCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建新服务提供商"""
    try:
        provider = await ProviderService.create(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "code": 201,
        "message": "created",
        "data": ProviderResponse.model_validate(provider),
    }


@router.put(
    "/{provider_id}",
    response_model=ApiResponse[ProviderResponse],
    summary="更新服务提供商",
)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """更新服务提供商信息"""
    provider = await ProviderService.update(db, provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="提供商不存在")
    return {
        "code": 200,
        "message": "success",
        "data": ProviderResponse.model_validate(provider),
    }


@router.delete(
    "/{provider_id}",
    response_model=ApiResponse[None],
    summary="删除服务提供商",
)
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """删除服务提供商（存在关联报价时拒绝）"""
    ok, reason = await ProviderService.delete(db, provider_id)
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="提供商不存在")
        raise HTTPException(status_code=400, detail=reason)
    return {"code": 200, "message": "deleted", "data": None}
