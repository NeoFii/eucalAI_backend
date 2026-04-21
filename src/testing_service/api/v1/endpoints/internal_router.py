"""Internal router-catalog endpoints for router-service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.internal import build_internal_auth_dependency
from testing_service.dependencies import get_db_session
from testing_service.config import get_settings
from testing_service.repositories import ModelRepository, OfferingRepository

settings = get_settings()
router = APIRouter(prefix="/internal/router", tags=["internal-router"])
verify_internal_secret = build_internal_auth_dependency(
    settings.internal_secret,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"router-service"},
)


class ResolveRoutesRequest(BaseModel):
    """Resolve route candidates for router-service."""

    model_name: str
    provider_hint: str | None = None

@router.get("/models")
async def list_router_models(
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    return await ModelRepository.list_router_models(db)


@router.post("/routes/resolve")
async def resolve_routes(
    payload: ResolveRoutesRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    return {
        "items": await OfferingRepository.resolve_router_routes(
            db,
            model_name=payload.model_name,
            provider_hint=payload.provider_hint,
        )
    }


@router.get("/offerings/{offering_id}")
async def get_router_offering(
    offering_id: int,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
):
    payload = await OfferingRepository.get_router_offering(db, offering_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="offering not found")
    return payload
