"""POST /internal/v1/classify — difficulty classification endpoint."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends

from common.observability import get_request_id
from inference_service.auth import require_inference_secret
from inference_service.schemas.classify import ClassifyRequest, ClassifyResponse

router = APIRouter()
logger = logging.getLogger("inference_service")

CLASSIFY_SOFT_TIMEOUT_SECONDS = 30.0


@router.post("/internal/v1/classify", response_model=ClassifyResponse)
async def classify(
    request: ClassifyRequest,
    _secret: str = Depends(require_inference_secret),
) -> ClassifyResponse:
    from inference_service.main import get_config_manager, get_engine

    engine = get_engine()
    config_manager = get_config_manager()
    config = config_manager.load()
    config_version = config_manager.config_version
    config_source = config_manager.config_source

    request_id = get_request_id() or request.request_id or ""

    t_start = time.monotonic()
    result = await asyncio.to_thread(
        engine.predict_chat_messages,
        request.messages,
        request_id=request_id,
        runtime_config=config,
    )
    elapsed = time.monotonic() - t_start
    latency_ms = round(elapsed * 1000, 2)

    if elapsed > CLASSIFY_SOFT_TIMEOUT_SECONDS:
        logger.warning(
            "classify took %.1fs (soft timeout %.1fs), request_id=%s",
            elapsed, CLASSIFY_SOFT_TIMEOUT_SECONDS, request_id,
        )

    return ClassifyResponse(
        request_id=result["request_id"],
        scores_0_2=result["scores_0_2"],
        proto_weighted_0_2=result.get("proto_weighted_0_2"),
        total_score_0_10=result["total_score_0_10"],
        score_source=result["score_source"],
        routing_tier=result["routing_tier"],
        selected_model=result["selected_model"],
        tier_model_map=result["tier_model_map"],
        score_bands_raw=result["score_bands_raw"],
        fallback_routes=result.get("fallback_routes", []),
        config_version=config_version,
        config_source=config_source,
        latency_ms=latency_ms,
    )
