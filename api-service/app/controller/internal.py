"""Internal HMAC-protected endpoints for service-to-service communication.

Phase 8-01: Exposes /routing-config/active/inference for inference-service.
Only the inference-service caller is allowed (D-03).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.http.internal_auth import build_internal_auth_dependency
from app.core.config import settings
from app.core.db import get_db
from app.service.admin.routing_setting_service import RoutingSettingService

router = APIRouter(prefix="/internal", tags=["internal"])

verify_routing_config_inference = build_internal_auth_dependency(
    settings.INTERNAL_SECRET,
    request_ttl_seconds=settings.INTERNAL_REQUEST_TTL_SECONDS,
    allowed_callers={"inference-service"},
)


class InternalRoutingConfigInference(BaseModel):
    """Response for /internal/routing-config/active/inference (inference-service)."""

    version: int
    status: str
    route_order: list[str]
    weights: dict[str, float]
    score_bands: str
    tier_model_map: dict[str, str]


@router.get(
    "/routing-config/active/inference",
    response_model=InternalRoutingConfigInference,
    summary="Active routing config for inference-service",
)
async def get_active_routing_config_inference(
    _: None = Depends(verify_routing_config_inference),
    db: AsyncSession = Depends(get_db),
) -> InternalRoutingConfigInference:
    """Return routing configuration subset needed by inference-service.

    HMAC-protected: only inference-service is allowed (D-03).
    """
    base = await RoutingSettingService.resolve_for_internal(db)
    return InternalRoutingConfigInference(
        version=0,
        status="active",
        route_order=base["route_order"],
        weights=base["weights"],
        score_bands=base["score_bands"],
        tier_model_map=base["tier_model_map"],
    )
