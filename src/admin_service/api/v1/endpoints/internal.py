"""Internal admin-service endpoints."""
# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.dependencies import get_db_session
from admin_service.repositories.admin_user_repository import AdminUserRepository
from admin_service.schemas.routing_config import (
    InternalRoutingConfigFull,
    InternalRoutingConfigInference,
)
from admin_service.services.routing_config_service import RoutingConfigService
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
    response_model=InternalRoutingConfigFull,
    summary="Active routing config for router-service",
)
async def get_active_routing_config_full(
    _: None = Depends(verify_routing_config_full),
    db: AsyncSession = Depends(get_db_session),
) -> InternalRoutingConfigFull:
    try:
        return await RoutingConfigService.resolve_active_full(db)
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
        return await RoutingConfigService.resolve_active_inference(db)
    except NotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
