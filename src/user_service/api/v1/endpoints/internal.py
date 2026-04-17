"""Internal user-service endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.internal import build_internal_auth_dependency
from user_service.config import settings
from user_service.dependencies import get_db_session
from user_service.models import User

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


@router.get("/users/by-id/{user_id}", response_model=InternalUserResponse, summary="Get user by database id")
async def get_user_by_id(
    user_id: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserResponse:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return InternalUserResponse(
        id=int(user.id),
        uid=int(user.uid),
        email=user.email,
        status=int(user.status),
    )


@router.get("/stats/users", response_model=InternalUserStatsResponse, summary="Get user stats")
async def get_user_stats(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUserStatsResponse:
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    return InternalUserStatsResponse(total_users=int(total_users))
