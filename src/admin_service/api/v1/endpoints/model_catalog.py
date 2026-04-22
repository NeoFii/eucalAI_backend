"""Public model catalog endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session
from admin_service.schemas.model_catalog import (
    ModelCategoryListResponse,
    ModelVendorListResponse,
    SupportedModelListResponse,
    SupportedModelResponse,
)
from admin_service.services.model_catalog_service import ModelCatalogService
from common.api import PaginatedResponse

router = APIRouter(tags=["model-catalog"])


@router.get(
    "/model-vendors",
    response_model=ModelVendorListResponse,
    summary="List model vendors",
)
async def list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorListResponse:
    items, total = await ModelCatalogService.list_vendors(
        db,
        page=page,
        page_size=page_size,
        active_only=True,
    )
    return ModelVendorListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.get(
    "/models/categories",
    response_model=ModelCategoryListResponse,
    summary="List model categories",
)
async def list_model_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryListResponse:
    items, total = await ModelCatalogService.list_categories(
        db,
        page=page,
        page_size=page_size,
        active_only=True,
    )
    return ModelCategoryListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/models", response_model=SupportedModelListResponse, summary="List models")
async def list_supported_models(
    category: str | None = None,
    vendors: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelListResponse:
    vendor_list = [item.strip() for item in (vendors or "").split(",") if item.strip()]
    items, total = await ModelCatalogService.list_models(
        db,
        category=category,
        vendors=vendor_list,
        q=q,
        page=page,
        page_size=page_size,
        active_only=True,
    )
    return SupportedModelListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/models/{slug}", response_model=SupportedModelResponse, summary="Get model detail")
async def get_supported_model(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelResponse:
    return SupportedModelResponse(
        data=await ModelCatalogService.get_model_by_slug(db, slug, active_only=True)
    )
