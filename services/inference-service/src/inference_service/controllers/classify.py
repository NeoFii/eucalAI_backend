"""POST /internal/v1/classify — difficulty classification endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from inference_service.core.dependencies import (
    get_config_manager,
    get_engine,
    require_inference_secret,
)
from inference_service.schemas.classify import ClassifyRequest, ClassifyResponse
from inference_service.services.classify_service import ClassifyService

router = APIRouter()


@router.post("/internal/v1/classify", response_model=ClassifyResponse)
async def classify(
    request: ClassifyRequest,
    _secret: str = Depends(require_inference_secret),
    engine=Depends(get_engine),
    config_manager=Depends(get_config_manager),
) -> ClassifyResponse:
    return await ClassifyService.classify(request, engine, config_manager)
