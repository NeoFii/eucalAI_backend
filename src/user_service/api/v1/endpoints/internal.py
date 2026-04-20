"""Internal user-service endpoints."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.internal import build_internal_auth_dependency
from user_service.config import settings
from user_service.dependencies import get_db_session
from user_service.models import User
from user_service.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/internal", tags=["internal"])
verify_internal_secret = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"admin-service", "router-service"},
)


class InternalUserResponse(BaseModel):
    id: int
    uid: int
    email: str
    status: int


class InternalUserStatsResponse(BaseModel):
    total_users: int


class InternalApiKeyValidateRequest(BaseModel):
    key: str
    model: str | None = None
    client_ip: str | None = None


class InternalApiKeyValidateResponse(BaseModel):
    id: int
    user_id: int
    name: str


@router.get("/users/{uid}", response_model=InternalUserResponse, summary="Get user by uid")
async def get_user_by_uid(
    uid: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserResponse:
    user = (await db.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return InternalUserResponse(
        id=int(user.id),
        uid=int(user.uid),
        email=user.email,
        status=int(user.status),
    )


@router.post(
    "/api-keys/validate",
    response_model=InternalApiKeyValidateResponse,
    summary="Validate user API key",
)
async def validate_api_key(
    payload: InternalApiKeyValidateRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalApiKeyValidateResponse:
    key_hash = hashlib.sha256(payload.key.encode("utf-8")).hexdigest()
    api_key = await ApiKeyService.validate_by_hash(
        db,
        key_hash,
        model=payload.model,
        client_ip=payload.client_ip,
    )
    return InternalApiKeyValidateResponse(
        id=int(api_key.id),
        user_id=int(api_key.user_id),
        name=api_key.name,
    )


@router.get("/stats/users", response_model=InternalUserStatsResponse, summary="Get user stats")
async def get_user_stats(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserStatsResponse:
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    return InternalUserStatsResponse(total_users=int(total_users))
