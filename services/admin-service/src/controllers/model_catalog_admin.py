"""Admin model catalog management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, get_request_meta
from models import AdminUser
from core.policies import require_active_admin, require_super_admin
from schemas.model_catalog import (
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
from services.model_catalog_service import ModelCatalogService
from utils.parsing import parse_comma_separated
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
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return ModelVendorResponse(
        data=await ModelCatalogService.create_vendor(
            db,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


@router.patch(
    "/vendors/{slug}",
    response_model=ModelVendorResponse,
    summary="Update catalog vendor",
)
async def update_model_vendor(
    payload: ModelVendorUpdate,
    http_request: Request,
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelVendorResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return ModelVendorResponse(
        data=await ModelCatalogService.update_vendor(
            db,
            slug,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


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
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return ModelCategoryResponse(
        data=await ModelCatalogService.create_category(
            db,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


@router.patch(
    "/categories/{key}",
    response_model=ModelCategoryResponse,
    summary="Update catalog category",
)
async def update_model_category(
    payload: ModelCategoryUpdate,
    http_request: Request,
    key: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCategoryResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return ModelCategoryResponse(
        data=await ModelCatalogService.update_category(
            db,
            key,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


@router.get("/models", response_model=SupportedModelListResponse, summary="List catalog models")
async def admin_list_supported_models(
    category: str | None = None,
    vendors: str | None = Query(default=None, max_length=500),
    q: str | None = Query(default=None, max_length=200),
    status: str = Query(
        default="active",
        pattern=r"^(active|archived|all)$",
        description="active=仅在线模型(默认) / archived=仅归档模型 / all=全部",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelListResponse:
    vendor_list = parse_comma_separated(vendors)
    items, total = await ModelCatalogService.list_models(
        db,
        category=category,
        vendors=vendor_list,
        q=q,
        page=page,
        page_size=page_size,
        active_only=False,
        status=status,
    )
    return SupportedModelListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.post("/models", response_model=SupportedModelResponse, summary="Create catalog model")
async def create_supported_model(
    payload: SupportedModelCreate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return SupportedModelResponse(
        data=await ModelCatalogService.create_model(
            db,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


@router.patch(
    "/models/{slug}",
    response_model=SupportedModelResponse,
    summary="Update catalog model",
)
async def update_supported_model(
    payload: SupportedModelUpdate,
    http_request: Request,
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SupportedModelResponse:
    ip_address, user_agent = get_request_meta(http_request)
    return SupportedModelResponse(
        data=await ModelCatalogService.update_model(
            db,
            slug,
            payload,
            actor_admin_id=current_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


@router.delete(
    "/models/{slug}",
    response_model=ModelCatalogOperationResponse,
    summary="Archive catalog model (soft delete)",
)
async def archive_supported_model(
    http_request: Request,
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ModelCatalogOperationResponse:
    """归档模型（软删除）：把 is_active 置为 False，记录可以在归档列表中恢复。"""
    ip_address, user_agent = get_request_meta(http_request)
    await ModelCatalogService.disable_model(
        db,
        slug,
        actor_admin_id=current_admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ModelCatalogOperationResponse(message="archived")
