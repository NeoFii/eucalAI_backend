"""Admin model catalog management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session
from admin_service.models import AdminUser
from admin_service.policies import require_active_admin, require_super_admin
from admin_service.schemas.model_catalog import (
    ModelCatalogOperationResponse,
    ModelCategoryCreate,
    ModelCategoryListResponse,
    ModelCategoryResponse,
    ModelCategoryUpdate,
    ModelVendorCreate,
    ModelVendorListResponse,
    ModelVendorResponse,
    ModelVendorUpdate,
    SupportedModelCreate,
    SupportedModelListResponse,
    SupportedModelResponse,
    SupportedModelUpdate,
)
from admin_service.services.model_catalog_service import ModelCatalogService
from common.api import PaginatedResponse

router = APIRouter(prefix="/model-catalog", tags=["admin-model-catalog"])


@router.get("/vendors", response_model=ModelVendorListResponse, summary="List catalog vendors")
async def admin_list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorListResponse:
    items, total = await ModelCatalogService.list_vendors(
        db,
        page=page,
        page_size=page_size,
        active_only=False,
    )
    return ModelVendorListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.post("/vendors", response_model=ModelVendorResponse, summary="Create catalog vendor")
async def create_model_vendor(
    payload: ModelVendorCreate,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorResponse:
    return ModelVendorResponse(data=await ModelCatalogService.create_vendor(db, payload))


@router.patch(
    "/vendors/{slug}",
    response_model=ModelVendorResponse,
    summary="Update catalog vendor",
)
async def update_model_vendor(
    slug: str,
    payload: ModelVendorUpdate,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorResponse:
    return ModelVendorResponse(data=await ModelCatalogService.update_vendor(db, slug, payload))


@router.get(
    "/categories",
    response_model=ModelCategoryListResponse,
    summary="List catalog categories",
)
async def admin_list_model_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryListResponse:
    items, total = await ModelCatalogService.list_categories(
        db,
        page=page,
        page_size=page_size,
        active_only=False,
    )
    return ModelCategoryListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.post(
    "/categories",
    response_model=ModelCategoryResponse,
    summary="Create catalog category",
)
async def create_model_category(
    payload: ModelCategoryCreate,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryResponse:
    return ModelCategoryResponse(data=await ModelCatalogService.create_category(db, payload))


@router.patch(
    "/categories/{key}",
    response_model=ModelCategoryResponse,
    summary="Update catalog category",
)
async def update_model_category(
    key: str,
    payload: ModelCategoryUpdate,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryResponse:
    return ModelCategoryResponse(data=await ModelCatalogService.update_category(db, key, payload))


@router.get("/models", response_model=SupportedModelListResponse, summary="List catalog models")
async def admin_list_supported_models(
    category: str | None = None,
    vendors: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_active_admin),
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
        active_only=False,
    )
    return SupportedModelListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.post("/models", response_model=SupportedModelResponse, summary="Create catalog model")
async def create_supported_model(
    payload: SupportedModelCreate,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelResponse:
    del current_admin
    return SupportedModelResponse(data=await ModelCatalogService.create_model(db, payload))


@router.patch(
    "/models/{slug}",
    response_model=SupportedModelResponse,
    summary="Update catalog model",
)
async def update_supported_model(
    slug: str,
    payload: SupportedModelUpdate,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelResponse:
    return SupportedModelResponse(data=await ModelCatalogService.update_model(db, slug, payload))


@router.delete(
    "/models/{slug}",
    response_model=ModelCatalogOperationResponse,
    summary="Disable catalog model",
)
async def disable_supported_model(
    slug: str,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCatalogOperationResponse:
    await ModelCatalogService.disable_model(db, slug)
    return ModelCatalogOperationResponse(message="disabled")
