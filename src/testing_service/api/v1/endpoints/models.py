# -*- coding: utf-8 -*-
"""Testing service model endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing_service.dependencies import AdminPrincipal, get_current_admin, get_db_session
from testing_service.catalog import CategoryService, ModelService
from testing_service.provider_config import OfferingService
from testing_service.schemas import (
    ApiResponse,
    ListResponse,
    ModelCategoryResponse,
    ModelCreate,
    ModelDetailResponse,
    ModelListItem,
    ModelOfferingResponse,
    ModelUpdate,
    ModelVendorBrief,
    OfferingCreate,
    ProviderBrief,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.get(
    "/categories",
    response_model=ApiResponse[ListResponse[ModelCategoryResponse]],
    summary="List model categories",
)
async def list_categories(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    categories = await CategoryService.list_all(db)
    items = [
        ModelCategoryResponse(
            id=category.id,
            key=category.key,
            name=category.name,
            sort_order=category.sort_order,
            is_active=category.is_active,
        )
        for category in categories
    ]
    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": len(items), "page": 1, "page_size": len(items)},
    }


@router.get(
    "/",
    response_model=ApiResponse[ListResponse[ModelListItem]],
    include_in_schema=False,
)
@router.get("", response_model=ApiResponse[ListResponse[ModelListItem]], summary="List models")
async def list_models(
    category: Optional[str] = Query(None, description="Category key"),
    vendors: Optional[str] = Query(None, description="Comma-separated vendor slugs"),
    q: Optional[str] = Query(None, description="Keyword search"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    vendor_slugs: Optional[List[str]] = (
        [slug.strip() for slug in vendors.split(",") if slug.strip()] if vendors else None
    )
    models, total = await ModelService.list_all(
        db=db,
        category_key=category,
        vendor_slugs=vendor_slugs,
        q=q,
        page=page,
        page_size=page_size,
    )
    provider_counts = await OfferingService.get_active_provider_counts(
        db,
        [int(model.id) for model in models],
    )

    items: list[ModelListItem] = []
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
                is_reasoning_model=model.is_reasoning_model,
                sort_order=model.sort_order,
                vendor=ModelVendorBrief(
                    id=model.vendor.id,
                    slug=model.vendor.slug,
                    name=model.vendor.name,
                    logo_url=model.vendor.logo_url,
                ),
                categories=category_briefs,
                provider_count=provider_counts.get(int(model.id), 0),
            )
        )

    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.get("/{slug}", response_model=ApiResponse[ModelDetailResponse], summary="Get model")
async def get_model(
    slug: str,
    n: int = Query(5, ge=1, le=20, description="Latest successful probes to aggregate"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        return {"code": 404, "message": "model not found", "data": None}

    category_briefs = await ModelService.get_category_briefs(db, model.id)
    offerings_orm = await OfferingService.list_by_model(db, model.id)

    offerings: list[ModelOfferingResponse] = []
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
                provider_model_id=offering.provider_model_name,
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


@router.get(
    "/{slug}/offerings",
    response_model=ApiResponse[List[ModelOfferingResponse]],
    summary="List all offerings for one model (admin)",
)
async def list_model_offerings(
    slug: str,
    n: int = Query(5, ge=1, le=20, description="Latest successful probes to aggregate"),
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        return {"code": 404, "message": "model not found", "data": []}

    offerings_orm = await OfferingService.list_all_by_model(db, model.id)
    offerings: list[ModelOfferingResponse] = []
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
                provider_model_id=offering.provider_model_name,
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
    summary="Add model offering",
)
async def add_model_offering(
    slug: str,
    data: OfferingCreate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    model = await ModelService.get_by_slug(db, slug)
    if not model:
        raise HTTPException(status_code=404, detail="model not found")
    try:
        offering = await OfferingService.create(db, model.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
            provider_model_id=offering.provider_model_name,
            price_updated_at=offering.price_updated_at,
            is_active=offering.is_active,
            metrics=None,
        ),
    }


@router.post("", response_model=ApiResponse[ModelDetailResponse], status_code=201, summary="Create model")
async def create_model(
    data: ModelCreate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        model = await ModelService.create(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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


@router.put("/{slug}", response_model=ApiResponse[ModelDetailResponse], summary="Update model")
async def update_model(
    slug: str,
    data: ModelUpdate,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    model = await ModelService.update(db, slug, data)
    if not model:
        raise HTTPException(status_code=404, detail="model not found")

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
