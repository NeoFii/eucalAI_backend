"""Internal admin-service endpoints."""
# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.dependencies import get_db_session
from admin_service.repositories.admin_user_repository import AdminUserRepository
from admin_service.schemas.routing_config import (
    InternalRoutingConfigFull,
    InternalRoutingConfigInference,
)
from admin_service.services.pool_service import PoolService
from admin_service.services.routing_setting_service import RoutingSettingService
from admin_service.services.model_catalog_service import ModelCatalogService
from admin_service.utils.parsing import parse_comma_separated
from common.core.exceptions import (
    NotFoundException,
    ValidationException,
)
from common.internal import build_internal_auth_dependency

router = APIRouter(prefix="/internal", tags=["internal"])
verify_internal_secret = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"user-service"},
)


class InternalAdminResponse(BaseModel):
    id: int
    uid: str
    email: str
    name: str
    role: str
    status: int


@router.get("/admins/{uid}", response_model=InternalAdminResponse, summary="Get admin by uid")
async def get_admin_by_uid(
    uid: str,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalAdminResponse:
    admin = await AdminUserRepository(db).get_by_uid(uid)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    return InternalAdminResponse(
        id=int(admin.id),
        uid=admin.uid,
        email=admin.email,
        name=admin.name,
        role=admin.role,
        status=int(admin.status),
    )


# ── Routing config internal endpoints (separate auth) ────────────────

verify_routing_config_full = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"router-service"},
)
verify_routing_config_inference = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"inference-service"},
)


@router.get(
    "/routing-config/active/full",
    summary="Active routing config for router-service (v2: from routing_settings + pools)",
)
async def get_active_routing_config_full(
    _: None = Depends(verify_routing_config_full),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        base = await RoutingSettingService.resolve_for_internal(db)
        tier_models = list(base["tier_model_map"].values())
        all_model_slugs = list(set(tier_models))
        model_channels = await PoolService.resolve_model_channels(db, all_model_slugs)
        model_prices = await ModelCatalogService.get_prices_by_slugs(db, all_model_slugs)
        return {
            **base,
            "model_channels": model_channels,
            "model_prices": model_prices,
        }
    except NotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
    except ValidationException as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc


@router.get(
    "/routing-config/active/inference",
    response_model=InternalRoutingConfigInference,
    summary="Active routing config for inference-service",
)
async def get_active_routing_config_inference(
    _: None = Depends(verify_routing_config_inference),
    db: AsyncSession = Depends(get_db_session),
) -> InternalRoutingConfigInference:
    try:
        base = await RoutingSettingService.resolve_for_internal(db)
        return InternalRoutingConfigInference(
            version=0,
            status="active",
            route_order=base["route_order"],
            weights=base["weights"],
            score_bands=base["score_bands"],
            tier_model_map=base["tier_model_map"],
        )
    except NotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc


# ── Model catalog internal endpoints ────────────────────────────────


@router.get("/model-catalog/vendors", summary="Internal: list model vendors")
async def internal_list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    items, total = await ModelCatalogService.list_vendors(
        db, page=page, page_size=page_size, active_only=True,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/model-catalog/categories", summary="Internal: list model categories")
async def internal_list_model_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    items, total = await ModelCatalogService.list_categories(
        db, page=page, page_size=page_size, active_only=True,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/model-catalog/models", summary="Internal: list models")
async def internal_list_models(
    category: str | None = None,
    vendors: str | None = Query(default=None, max_length=500),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    vendor_list = parse_comma_separated(vendors)
    items, total = await ModelCatalogService.list_models(
        db,
        category=category,
        vendors=vendor_list,
        q=q,
        page=page,
        page_size=page_size,
        active_only=True,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/model-catalog/models/{slug}", summary="Internal: get model detail")
async def internal_get_model(
    slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    detail = await ModelCatalogService.get_model_by_slug(db, slug, active_only=True)
    return {
        "code": 200,
        "message": "success",
        "data": detail.model_dump(mode="json"),
    }
