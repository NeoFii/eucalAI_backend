"""Core internal endpoints: user lookup, API key validation, stats."""

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.internal import build_internal_auth_dependency
from core.config import settings
from core.dependencies import get_db_session
from repositories.api_key_repository import ApiKeyRepository
from repositories.user_repository import UserRepository
from schemas.internal import (
    InternalApiKeyValidateRequest,
    InternalApiKeyValidateResponse,
    InternalUserResponse,
    InternalUserStatsResponse,
)
from services.api_key_service import ApiKeyService

logger = logging.getLogger("user_service.internal")

router = APIRouter(prefix="/internal", tags=["internal"])
verify_internal_secret = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"admin-service", "router-service"},
)
verify_router_only = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"router-service"},
)


@router.get("/users/{uid}", response_model=InternalUserResponse, summary="Get user by uid")
async def get_user_by_uid(
    uid: str = Path(min_length=1),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserResponse:
    user = await UserRepository(db).get_by_uid(uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return InternalUserResponse(
        id=int(user.id),
        uid=user.uid,
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
    user = await UserRepository(db).get_by_id(api_key.user_id)
    return InternalApiKeyValidateResponse(
        id=int(api_key.id),
        user_id=int(api_key.user_id),
        name=api_key.name,
        balance=int(user.balance) if user else 0,
        rpm_limit=api_key.rpm_limit,
    )


@router.get("/stats/users", response_model=InternalUserStatsResponse, summary="Get user stats")
async def get_user_stats(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserStatsResponse:
    total_users = await UserRepository(db).count_all()
    return InternalUserStatsResponse(total_users=total_users)
