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
from admin_service.services.invitation_service import InvitationCodeService
from admin_service.services.routing_config_service import RoutingConfigService
from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
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
    uid: int
    email: str
    name: str
    role: str
    status: int


class InternalInvitationConsumeRequest(BaseModel):
    code: str
    used_by_uid: int


class InternalInvitationConsumeResponse(BaseModel):
    consumed: bool = True


class InternalInvitationReleaseRequest(BaseModel):
    code: str
    used_by_uid: int


class InternalInvitationReleaseResponse(BaseModel):
    released: bool


@router.get("/admins/{uid}", response_model=InternalAdminResponse, summary="Get admin by uid")
async def get_admin_by_uid(
    uid: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalAdminResponse:
    admin = await AdminUserRepository(db).get_by_uid(uid)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    return InternalAdminResponse(
        id=int(admin.id),
        uid=int(admin.uid),
        email=admin.email,
        name=admin.name,
        role=admin.role,
        status=int(admin.status),
    )


@router.post(
    "/invitation-codes/consume",
    response_model=InternalInvitationConsumeResponse,
    summary="Consume invitation code",
)
async def consume_invitation_code(
    payload: InternalInvitationConsumeRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalInvitationConsumeResponse:
    try:
        await InvitationCodeService.verify_and_use(db, payload.code, payload.used_by_uid)
    except InvalidInvitationCodeException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
    except InvitationCodeUsedException as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
    except InvitationCodeDisabledException as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc
    except InvitationCodeExpiredException as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=exc.detail) from exc
    return InternalInvitationConsumeResponse()


@router.post(
    "/invitation-codes/release",
    response_model=InternalInvitationReleaseResponse,
    summary="Release invitation code",
)
async def release_invitation_code(
    payload: InternalInvitationReleaseRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalInvitationReleaseResponse:
    try:
        released = await InvitationCodeService.release(db, payload.code, payload.used_by_uid)
    except InvalidInvitationCodeException:
        released = False
    return InternalInvitationReleaseResponse(released=released)


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
