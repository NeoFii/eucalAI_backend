# -*- coding: utf-8 -*-
"""
Testing 服务供应商管理端点
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.schemas import (
    ProviderCreate,
    ProviderResponse,
    ProviderWithModels,
    ProviderStatsResponse,
    ListResponse,
)
from testing.services import (
    ProviderService,
    ModelProviderService,
    ModelService,
    BenchmarkService,
)

router = APIRouter(prefix="/providers", tags=["供应商管理"])


@router.get(
    "/",
    response_model=ListResponse,
    summary="获取供应商列表",
    description="获取所有活跃的供应商",
)
async def list_providers(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取供应商列表"""
    providers = await ProviderService.list_all(db)

    items = []
    for provider in providers:
        model_count = await ProviderService.get_model_count(db, provider.id)
        items.append({
            "id": provider.id,
            "provider_id": provider.provider_id,
            "name": provider.name,
            "name_zh": provider.name_zh,
            "logo_url": provider.logo_url,
            "color": provider.color,
            "is_active": provider.is_active,
            "sort_order": provider.sort_order,
            "model_count": model_count,
        })

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items),
    }


@router.get(
    "/{provider_id}",
    response_model=ProviderWithModels,
    summary="获取供应商详情",
    description="根据ID获取供应商详情",
)
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取供应商详情"""
    provider = await ProviderService.get_by_id(db, provider_id)
    if not provider:
        return {"code": 404, "message": "供应商不存在"}

    model_count = await ProviderService.get_model_count(db, provider.id)

    return {
        "id": provider.id,
        "provider_id": provider.provider_id,
        "name": provider.name,
        "name_zh": provider.name_zh,
        "logo_url": provider.logo_url,
        "color": provider.color,
        "is_active": provider.is_active,
        "sort_order": provider.sort_order,
        "model_count": model_count,
    }


@router.post(
    "/",
    response_model=ProviderResponse,
    summary="创建供应商",
    description="创建新的供应商",
)
async def create_provider(
    request: ProviderCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建供应商"""
    provider = await ProviderService.create(
        db=db,
        provider_id=request.provider_id,
        name=request.name,
        name_zh=request.name_zh,
        logo_url=request.logo_url,
        color=request.color,
        is_active=request.is_active,
        sort_order=request.sort_order,
    )

    return {
        "id": provider.id,
        "provider_id": provider.provider_id,
        "name": provider.name,
        "name_zh": provider.name_zh,
        "logo_url": provider.logo_url,
        "color": provider.color,
        "is_active": provider.is_active,
        "sort_order": provider.sort_order,
    }


@router.get(
    "/{provider_id}/stats",
    response_model=ListResponse,
    summary="获取供应商性能统计",
    description="获取供应商的性能统计数据",
)
async def get_provider_stats(
    provider_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取供应商性能统计"""
    provider = await ProviderService.get_by_id(db, provider_id)
    if not provider:
        return {"code": 404, "message": "供应商不存在"}

    stats_list = await BenchmarkService.get_provider_stats(db, provider_id)

    items = []
    for item in stats_list:
        model = await ModelService.get_by_id(db, item["model_id"])
        items.append({
            "provider_id": provider.id,
            "provider_name": provider.name,
            "color": provider.color,
            "model_provider_id": item["model_provider_id"],
            "model_name": model.name if model else None,
            "api_model_name": item["api_model_name"],
            "input_price_cny_1m": item["input_price_cny_1m"],
            "output_price_cny_1m": item["output_price_cny_1m"],
            "stats": item["stats"],
        })

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items),
    }
