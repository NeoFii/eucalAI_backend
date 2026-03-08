# -*- coding: utf-8 -*-
"""
Testing 服务模型管理端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryWithModels,
    ModelCreate,
    ModelUpdate,
    ModelListItem,
    ModelDetailResponse,
    ProviderCreate,
    ProviderResponse,
    ProviderWithModels,
    ProviderStatsResponse,
    BenchmarkStatsResponse,
    ListResponse,
    BaseResponse,
)
from testing.services import (
    CategoryService,
    ModelService,
    ProviderService,
    ModelProviderService,
    BenchmarkService,
)
from sqlalchemy import func, select

from testing.models import ModelCategoryMapping

router = APIRouter(prefix="/models", tags=["模型管理"])


# ========== 分类端点 ==========

@router.get(
    "/categories",
    response_model=ListResponse,
    summary="获取分类列表",
    description="获取所有模型分类",
)
async def list_categories(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取所有分类"""
    categories = await CategoryService.list_all(db)

    # 获取每个分类的模型数量
    items = []
    for cat in categories:
        # 使用数据库查询获取模型数量，避免懒加载问题
        count_result = await db.execute(
            select(func.count()).select_from(ModelCategoryMapping).where(
                ModelCategoryMapping.category_id == cat.id
            )
        )
        model_count = count_result.scalar() or 0

        items.append({
            "id": cat.id,
            "name_zh": cat.name_zh,
            "name_en": cat.name_en,
            "slug": cat.slug,
            "description_zh": cat.description_zh,
            "description_en": cat.description_en,
            "icon": cat.icon,
            "sort_order": cat.sort_order,
            "model_count": model_count,
        })

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items),
    }


@router.get(
    "/categories/{slug}",
    response_model=CategoryWithModels,
    summary="获取分类详情",
    description="根据slug获取分类详情",
)
async def get_category(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取分类详情"""
    category = await CategoryService.get_by_slug(db, slug)
    if not category:
        return {"code": 404, "message": "分类不存在"}

    # 使用数据库查询获取模型数量
    count_result = await db.execute(
        select(func.count()).select_from(ModelCategoryMapping).where(
            ModelCategoryMapping.category_id == category.id
        )
    )
    model_count = count_result.scalar() or 0

    return {
        "id": category.id,
        "name_zh": category.name_zh,
        "name_en": category.name_en,
        "slug": category.slug,
        "description_zh": category.description_zh,
        "description_en": category.description_en,
        "icon": category.icon,
        "sort_order": category.sort_order,
        "model_count": model_count,
    }


@router.post(
    "/categories",
    response_model=CategoryResponse,
    summary="创建分类",
    description="创建新的模型分类",
)
async def create_category(
    request: CategoryCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建分类"""
    category = await CategoryService.create(
        db=db,
        name_zh=request.name_zh,
        name_en=request.name_en,
        slug=request.slug,
        description_zh=request.description_zh,
        description_en=request.description_en,
        icon=request.icon,
        sort_order=request.sort_order,
    )

    return {
        "id": category.id,
        "name_zh": category.name_zh,
        "name_en": category.name_en,
        "slug": category.slug,
        "description_zh": category.description_zh,
        "description_en": category.description_en,
        "icon": category.icon,
        "sort_order": category.sort_order,
    }


# ========== 模型端点 ==========

@router.get(
    "/",
    response_model=ListResponse,
    summary="获取模型列表",
    description="获取模型列表，支持分类筛选和分页",
)
async def list_models(
    category: Optional[str] = Query(None, description="分类slug"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取模型列表"""
    models, total = await ModelService.list_all(
        db=db,
        category_slug=category,
        page=page,
        page_size=page_size,
    )

    items = []
    for model in models:
        tags = await ModelService.get_tags(db, model.id)
        categories = await ModelService.get_categories_info(db, model.id)
        provider_count = await ModelService.get_provider_count(db, model.id)

        primary_cat = categories[0] if categories else None

        items.append({
            "id": model.id,
            "model_id": model.model_id,
            "name": model.name,
            "name_zh": model.name_zh,
            "description_zh": model.description_zh,
            "context_length": model.context_length,
            "model_size": model.model_size,
            "is_open_source": model.is_open_source,
            "tags": tags,
            "category": primary_cat,
            "provider_count": provider_count,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{model_id}",
    response_model=ModelDetailResponse,
    summary="获取模型详情",
    description="根据model_id获取模型详情",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取模型详情"""
    model = await ModelService.get_by_model_id(db, model_id)
    if not model:
        return {"code": 404, "message": "模型不存在"}

    tags = await ModelService.get_tags(db, model.id)
    categories = await ModelService.get_categories_info(db, model.id)

    return {
        "id": model.id,
        "model_id": model.model_id,
        "name": model.name,
        "name_zh": model.name_zh,
        "description_zh": model.description_zh,
        "description_en": model.description_en,
        "context_length": model.context_length,
        "model_size": model.model_size,
        "is_open_source": model.is_open_source,
        "is_active": model.is_active,
        "tags": tags,
        "categories": categories,
    }


@router.post(
    "/",
    response_model=ModelDetailResponse,
    summary="创建模型",
    description="创建新的模型",
)
async def create_model(
    request: ModelCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建模型"""
    model = await ModelService.create(
        db=db,
        model_id=request.model_id,
        name=request.name,
        name_zh=request.name_zh,
        description_zh=request.description_zh,
        description_en=request.description_en,
        context_length=request.context_length,
        model_size=request.model_size,
        is_open_source=request.is_open_source,
        is_active=request.is_active,
        category_ids=request.category_ids,
        tag_names=request.tag_names,
    )

    return {
        "id": model.id,
        "model_id": model.model_id,
        "name": model.name,
        "name_zh": model.name_zh,
        "description_zh": model.description_zh,
        "description_en": model.description_en,
        "context_length": model.context_length,
        "model_size": model.model_size,
        "is_open_source": model.is_open_source,
        "is_active": model.is_active,
        "tags": request.tag_names,
        "categories": [],
    }


@router.get(
    "/{model_id}/providers",
    response_model=ListResponse,
    summary="获取模型的供应商",
    description="获取指定模型的所有供应商配置",
)
async def get_model_providers(
    model_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取模型的供应商列表"""
    model = await ModelService.get_by_model_id(db, model_id)
    if not model:
        return {"code": 404, "message": "模型不存在"}

    model_providers = await ModelProviderService.list_by_model(db, model.id)

    items = []
    for mp in model_providers:
        provider = await ProviderService.get_by_id(db, mp.provider_id)
        stats = await BenchmarkService.get_stats(db, mp.id)

        items.append({
            "provider_id": provider.provider_id if provider else None,
            "provider_name": provider.name if provider else None,
            "provider_name_zh": provider.name_zh if provider else None,
            "color": provider.color if provider else None,
            "api_model_name": mp.api_model_name,
            "routing_alias": mp.routing_alias,
            "input_price_cny_1m": float(mp.input_price_cny_1m) if mp.input_price_cny_1m else None,
            "output_price_cny_1m": float(mp.output_price_cny_1m) if mp.output_price_cny_1m else None,
            "rate_limit_rpm": mp.rate_limit_rpm,
            "is_default": mp.is_default,
            "stats": stats,
        })

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items),
    }
