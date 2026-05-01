"""Admin pool management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, get_request_meta
from models import AdminUser
from core.policies import require_super_admin
from schemas.common import AdminBaseResponse
from schemas.pool import (
    AvailableModelSlugsResponse,
    CheckBalancesResponse,
    PoolAccountCreate,
    PoolAccountResponse,
    PoolAccountUpdate,
    PoolCreate,
    PoolDetailResponse,
    PoolListResponse,
    PoolModelCreate,
    PoolModelResponse,
    PoolModelUpdate,
    PoolResponse,
    PoolUpdate,
    SyncModelsResponse,
)
from services.pool_service import PoolService
from common.api import PaginatedResponse

router = APIRouter(prefix="/pools", tags=["admin-pools"])

_SLUG_PATH = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
_MODEL_SLUG_PATH = Path(..., max_length=120)


# ------------------------------------------------------------------
# Pool
# ------------------------------------------------------------------

@router.post("", response_model=PoolResponse, summary="Create pool")
async def create_pool(
    payload: PoolCreate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.create_pool(
        db, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolResponse(data=item)


@router.get("", response_model=PoolListResponse, summary="List pools")
async def list_pools(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolListResponse:
    items, total = await PoolService.list_pools(db, page=page, page_size=page_size)
    return PoolListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.get(
    "/available-models",
    response_model=AvailableModelSlugsResponse,
    summary="List model slugs with active pool coverage",
)
async def list_available_model_slugs(
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AvailableModelSlugsResponse:
    items = await PoolService.get_available_model_slugs(db)
    return AvailableModelSlugsResponse(data=items)


@router.get("/{slug}", response_model=PoolDetailResponse, summary="Pool detail")
async def get_pool(
    slug: str = _SLUG_PATH,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolDetailResponse:
    detail = await PoolService.get_pool(db, slug)
    return PoolDetailResponse(data=detail)


@router.patch("/{slug}", response_model=PoolResponse, summary="Update pool")
async def update_pool(
    payload: PoolUpdate,
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.update_pool(
        db, slug, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolResponse(data=item)


@router.delete("/{slug}", response_model=PoolResponse, summary="Disable pool")
async def disable_pool(
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.disable_pool(
        db, slug, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolResponse(data=item)


# ------------------------------------------------------------------
# PoolModel
# ------------------------------------------------------------------
@router.post("/{slug}/models", response_model=PoolModelResponse, summary="Add pool model")
async def add_pool_model(
    payload: PoolModelCreate,
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolModelResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.add_pool_model(
        db, slug, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolModelResponse(data=item)


@router.patch(
    "/{slug}/models/{model_slug}",
    response_model=PoolModelResponse, summary="Update pool model",
)
async def update_pool_model(
    payload: PoolModelUpdate,
    http_request: Request,
    slug: str = _SLUG_PATH,
    model_slug: str = _MODEL_SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolModelResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.update_pool_model(
        db, slug, model_slug, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolModelResponse(data=item)


@router.delete("/{slug}/models/{model_slug}", summary="Remove pool model")
async def remove_pool_model(
    http_request: Request,
    slug: str = _SLUG_PATH,
    model_slug: str = _MODEL_SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    ip_address, user_agent = get_request_meta(http_request)
    await PoolService.remove_pool_model(
        db, slug, model_slug, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return AdminBaseResponse()


@router.post("/{slug}/models/sync", response_model=SyncModelsResponse, summary="Sync models from upstream")
async def sync_models(
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SyncModelsResponse:
    ip_address, user_agent = get_request_meta(http_request)
    result = await PoolService.sync_models(
        db, slug, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return SyncModelsResponse(data=result)


# ------------------------------------------------------------------
# PoolAccount
# ------------------------------------------------------------------

@router.post("/{slug}/accounts", response_model=PoolAccountResponse, summary="Add pool account")
async def add_pool_account(
    payload: PoolAccountCreate,
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolAccountResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.add_pool_account(
        db, slug, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolAccountResponse(data=item)


@router.patch(
    "/{slug}/accounts/{account_id}",
    response_model=PoolAccountResponse, summary="Update pool account",
)
async def update_pool_account(
    payload: PoolAccountUpdate,
    http_request: Request,
    slug: str = _SLUG_PATH,
    account_id: int = Path(...),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolAccountResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.update_pool_account(
        db, slug, account_id, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolAccountResponse(data=item)


@router.delete(
    "/{slug}/accounts/{account_id}",
    response_model=PoolAccountResponse, summary="Disable pool account",
)
async def disable_pool_account(
    http_request: Request,
    slug: str = _SLUG_PATH,
    account_id: int = Path(...),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolAccountResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await PoolService.disable_pool_account(
        db, slug, account_id, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return PoolAccountResponse(data=item)


@router.post("/{slug}/accounts/check", response_model=CheckBalancesResponse, summary="Check account balances")
async def check_balances(
    http_request: Request,
    slug: str = _SLUG_PATH,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CheckBalancesResponse:
    ip_address, user_agent = get_request_meta(http_request)
    result = await PoolService.check_balances(
        db, slug, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return CheckBalancesResponse(data=result)
