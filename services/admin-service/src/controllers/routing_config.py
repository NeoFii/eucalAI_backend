"""Admin routing configuration management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, get_request_meta
from models import AdminUser
from core.policies import require_super_admin
from schemas.routing_config import (
    CredentialCreate,
    CredentialListResponse,
    CredentialResponse,
    CredentialUpdate,
    RoutingConfigCreate,
    RoutingConfigListResponse,
    RoutingConfigResponse,
    RoutingConfigUpdate,
)
from services.routing_config_service import RoutingConfigService
from common.api import PaginatedResponse

router = APIRouter(prefix="/routing-config", tags=["admin-routing-config"])


# ── Credential endpoints ─────────────────────────────────────────────


@router.post("/credentials", response_model=CredentialResponse, summary="Create credential")
async def create_credential(
    payload: CredentialCreate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.create_credential(
        db, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return CredentialResponse(data=item)


@router.get("/credentials", response_model=CredentialListResponse, summary="List credentials")
async def list_credentials(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CredentialListResponse:
    items, total = await RoutingConfigService.list_credentials(db, page=page, page_size=page_size)
    return CredentialListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.patch(
    "/credentials/{slug}", response_model=CredentialResponse, summary="Update credential"
)
async def update_credential(
    slug: str,
    payload: CredentialUpdate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.update_credential(
        db, slug, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return CredentialResponse(data=item)


@router.delete(
    "/credentials/{slug}", response_model=CredentialResponse, summary="Disable credential"
)
async def disable_credential(
    slug: str,
    http_request: Request,
    force: bool = Query(False),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.disable_credential(
        db, slug, force=force, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return CredentialResponse(data=item)


# ── Config version endpoints ─────────────────────────────────────────


@router.post("/versions", response_model=RoutingConfigResponse, summary="Create draft version")
async def create_version(
    payload: RoutingConfigCreate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.create_version(
        db, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingConfigResponse(data=item)


@router.get("/versions", response_model=RoutingConfigListResponse, summary="List versions")
async def list_versions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigListResponse:
    items, total = await RoutingConfigService.list_versions(db, page=page, page_size=page_size)
    return RoutingConfigListResponse(
        data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
    )


@router.get(
    "/versions/active", response_model=RoutingConfigResponse, summary="Get active version"
)
async def get_active_version(
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    item = await RoutingConfigService.get_active(db)
    return RoutingConfigResponse(data=item)


@router.get(
    "/versions/{version}", response_model=RoutingConfigResponse, summary="Get version by number"
)
async def get_version(
    version: int,
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    item = await RoutingConfigService.get_version(db, version)
    return RoutingConfigResponse(data=item)


@router.put(
    "/versions/{version}", response_model=RoutingConfigResponse, summary="Update draft version"
)
async def update_version(
    version: int,
    payload: RoutingConfigUpdate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.update_version(
        db, version, payload, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingConfigResponse(data=item)


@router.post(
    "/versions/{version}/publish",
    response_model=RoutingConfigResponse,
    summary="Publish version",
)
async def publish_version(
    version: int,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.publish_version(
        db, version, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingConfigResponse(data=item)


@router.post(
    "/versions/{version}/rollback",
    response_model=RoutingConfigResponse,
    summary="Rollback to version",
)
async def rollback_to_version(
    version: int,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingConfigResponse:
    ip_address, user_agent = get_request_meta(http_request)
    item = await RoutingConfigService.rollback_to_version(
        db, version, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingConfigResponse(data=item)
