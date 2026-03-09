# -*- coding: utf-8 -*-
"""
Testing 服务模型管理端点
提供模型列表、详情（含报价和性能指标）和分类列表查询
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.schemas import (
    ApiResponse,
    ListResponse,
    ModelCategoryResponse,
    ModelListItem,
    ModelDetailResponse,
    ModelVendorBrief,
    ProviderBrief,
    ModelOfferingResponse,
    ModelCreate,
    ModelUpdate,
    OfferingCreate,
)
from testing.services import (
    CategoryService,
    ModelService,
    OfferingService,
)

router = APIRouter(prefix="/models", tags=["模型管理"])


# ========== 分类端点 ==========

@router.get(
    "/categories",
    response_model=ApiResponse[ListResponse[ModelCategoryResponse]],
    summary="获取分类列表",
    description="获取所有启用的模型能力分类，按 sort_order 排序",
)
async def list_categories(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取所有分类"""
    categories = await CategoryService.list_all(db)
    items = [
        ModelCategoryResponse(
            id=cat.id,
            key=cat.key,
            name=cat.name,
            sort_order=cat.sort_order,
            is_active=cat.is_active,
        )
        for cat in categories
    ]
    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": len(items), "page": 1, "page_size": len(items)},
    }


# ========== 模型列表端点 ==========

@router.get(
    "",
    response_model=ApiResponse[ListResponse[ModelListItem]],
    summary="获取模型列表",
    description=(
        "获取模型列表，支持三个维度筛选（AND 逻辑）：\n"
        "- category：分类键筛选（如 reasoning / coding）\n"
        "- vendors：研发商 slug 多选，逗号分隔（如 anthropic,openai）\n"
        "- q：关键词搜索（匹配 name / slug / description）\n\n"
        "排序：分类内按 model_category_map.sort_order → models.sort_order → name"
    ),
)
async def list_models(
    category: Optional[str] = Query(None, description="分类键，如 reasoning / coding"),
    vendors: Optional[str] = Query(None, description="研发商 slug 多选，逗号分隔，如 anthropic,openai"),
    q: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取模型列表"""
    vendor_slugs: Optional[List[str]] = (
        [s.strip() for s in vendors.split(",") if s.strip()] if vendors else None
    )

    models, total = await ModelService.list_all(
        db=db,
        category_key=category,
        vendor_slugs=vendor_slugs,
        q=q,
        page=page,
        page_size=page_size,
    )

    items = []
    for model in models:
        category_briefs = await ModelService.get_category_briefs(db, model.id)
        items.append(
            ModelListItem(
                id=model.id,
                slug=model.slug,
                name=model.name,
                description=model.description,
                capability_tags=model.capability_tags or [],
                context_window=model.context_window,
                max_output_tokens=model.max_output_tokens,
                knowledge_cutoff=model.knowledge_cutoff,
                is_reasoning_model=model.is_reasoning_model,
                sort_order=model.sort_order,
                vendor=ModelVendorBrief(
                    id=model.vendor.id,
                    slug=model.vendor.slug,
                    name=model.vendor.name,
                    logo_url=model.vendor.logo_url,
                ),
                categories=category_briefs,
            )
        )

    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


# ========== 模型详情端点 ==========

@router.get(
    "/{slug}",
    response_model=ApiResponse[ModelDetailResponse],
    summary="获取模型详情",
    description="根据 slug 获取模型详情，附带所有提供商报价和近 N 次性能指标均值",
)
async def get_model(
    slug: str,
    n: int = Query(5, ge=1, le=20, description="聚合最近 N 次成功探测（默认 5）"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取模型详情（含报价和性能指标）"""
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        return {"code": 404, "message": "模型不存在", "data": None}

    category_briefs = await ModelService.get_category_briefs(db, model.id)
    offerings_orm = await OfferingService.list_by_model(db, model.id)

    # 组装每个报价的响应（含性能指标）
    offerings: List[ModelOfferingResponse] = []
    for offering in offerings_orm:
        metrics_list = await OfferingService.get_metrics(db, offering.id, n=n)
        # 取第一个区域的指标作为默认（若有多区域，前端可按需展示所有区域）
        metrics = metrics_list[0] if metrics_list else None
        offerings.append(
            ModelOfferingResponse(
                id=offering.id,
                provider=ProviderBrief(
                    id=offering.provider.id,
                    slug=offering.provider.slug,
                    name=offering.provider.name,
                    logo_url=offering.provider.logo_url,
                ),
                price_input_per_m=offering.price_input_per_m,
                price_output_per_m=offering.price_output_per_m,
                provider_model_id=offering.provider_model_id,
                price_updated_at=offering.price_updated_at,
                is_active=offering.is_active,
                metrics=metrics,
            )
        )

    return {
        "code": 200,
        "message": "success",
        "data": ModelDetailResponse(
            id=model.id,
            slug=model.slug,
            name=model.name,
            description=model.description,
            capability_tags=model.capability_tags or [],
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            knowledge_cutoff=model.knowledge_cutoff,
            is_reasoning_model=model.is_reasoning_model,
            is_active=model.is_active,
            vendor=ModelVendorBrief(
                id=model.vendor.id,
                slug=model.vendor.slug,
                name=model.vendor.name,
                logo_url=model.vendor.logo_url,
            ),
            categories=category_briefs,
            offerings=offerings,
        ),
    }


# ========== 模型写操作端点 ==========


# ---------- offerings 管理（管理端专用）----------

@router.get(
    "/{slug}/offerings",
    response_model=ApiResponse[List[ModelOfferingResponse]],
    summary="获取模型所有报价配置（管理端）",
    description="返回该模型的全部报价配置（含已废弃），供管理员查看",
)
async def list_model_offerings(
    slug: str,
    n: int = Query(5, ge=1, le=20, description="聚合最近 N 次探测（默认 5）"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """管理端：获取模型全部报价（含废弃），附带性能指标"""
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        return {"code": 404, "message": "模型不存在", "data": []}

    offerings_orm = await OfferingService.list_all_by_model(db, model.id)
    offerings: List[ModelOfferingResponse] = []
    for offering in offerings_orm:
        metrics_list = await OfferingService.get_metrics(db, offering.id, n=n)
        metrics = metrics_list[0] if metrics_list else None
        offerings.append(
            ModelOfferingResponse(
                id=offering.id,
                provider=ProviderBrief(
                    id=offering.provider.id,
                    slug=offering.provider.slug,
                    name=offering.provider.name,
                    logo_url=offering.provider.logo_url,
                ),
                price_input_per_m=offering.price_input_per_m,
                price_output_per_m=offering.price_output_per_m,
                provider_model_id=offering.provider_model_id,
                price_updated_at=offering.price_updated_at,
                is_active=offering.is_active,
                metrics=metrics,
            )
        )
    return {"code": 200, "message": "success", "data": offerings}


@router.post(
    "/{slug}/offerings",
    response_model=ApiResponse[ModelOfferingResponse],
    status_code=201,
    summary="为模型添加服务商报价",
)
async def add_model_offering(
    slug: str,
    data: OfferingCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """为指定模型添加服务商报价配置"""
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    try:
        offering = await OfferingService.create(db, model.id, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "code": 201,
        "message": "created",
        "data": ModelOfferingResponse(
            id=offering.id,
            provider=ProviderBrief(
                id=offering.provider.id,
                slug=offering.provider.slug,
                name=offering.provider.name,
                logo_url=offering.provider.logo_url,
            ),
            price_input_per_m=offering.price_input_per_m,
            price_output_per_m=offering.price_output_per_m,
            provider_model_id=offering.provider_model_id,
            price_updated_at=offering.price_updated_at,
            is_active=offering.is_active,
            metrics=None,
        ),
    }


# ========== 模型写操作端点 ==========

@router.post(
    "",
    response_model=ApiResponse[ModelDetailResponse],
    status_code=201,
    summary="创建模型",
)
async def create_model(
    data: ModelCreate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """创建新模型（含分类关联）"""
    try:
        model = await ModelService.create(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    category_briefs = await ModelService.get_category_briefs(db, model.id)
    return {
        "code": 201,
        "message": "created",
        "data": ModelDetailResponse(
            id=model.id,
            slug=model.slug,
            name=model.name,
            description=model.description,
            capability_tags=model.capability_tags or [],
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            knowledge_cutoff=model.knowledge_cutoff,
            is_reasoning_model=model.is_reasoning_model,
            is_active=model.is_active,
            vendor=ModelVendorBrief(
                id=model.vendor.id,
                slug=model.vendor.slug,
                name=model.vendor.name,
                logo_url=model.vendor.logo_url,
            ),
            categories=category_briefs,
            offerings=[],
        ),
    }


@router.put(
    "/{slug}",
    response_model=ApiResponse[ModelDetailResponse],
    summary="更新模型",
)
async def update_model(
    slug: str,
    data: ModelUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """更新模型字段（含可选分类关联替换）"""
    model = await ModelService.update(db, slug, data)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    category_briefs = await ModelService.get_category_briefs(db, model.id)
    return {
        "code": 200,
        "message": "success",
        "data": ModelDetailResponse(
            id=model.id,
            slug=model.slug,
            name=model.name,
            description=model.description,
            capability_tags=model.capability_tags or [],
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            knowledge_cutoff=model.knowledge_cutoff,
            is_reasoning_model=model.is_reasoning_model,
            is_active=model.is_active,
            vendor=ModelVendorBrief(
                id=model.vendor.id,
                slug=model.vendor.slug,
                name=model.vendor.name,
                logo_url=model.vendor.logo_url,
            ),
            categories=category_briefs,
            offerings=[],
        ),
    }


@router.delete(
    "/{slug}",
    response_model=ApiResponse[None],
    summary="删除模型（软删除）",
)
async def delete_model(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """软删除模型（设置 is_active=False）"""
    ok, reason = await ModelService.delete(db, slug)
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="模型不存在")
        raise HTTPException(status_code=400, detail=reason)
    return {"code": 200, "message": "deleted", "data": None}
