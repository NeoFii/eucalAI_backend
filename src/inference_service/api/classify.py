"""POST /internal/v1/classify — difficulty classification endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from inference_service.auth import require_inference_secret
from inference_service.schemas.classify import ClassifyRequest, ClassifyResponse

router = APIRouter()


@router.post("/internal/v1/classify", response_model=ClassifyResponse)
def classify(
    request: ClassifyRequest,
    _secret: str = Depends(require_inference_secret),
) -> ClassifyResponse:
    from inference_service.main import get_engine, get_runtime_store

    engine = get_engine()
    config = get_runtime_store().load()

    result = engine.predict_chat_messages(
        request.messages,
        request_id=request.request_id,
        runtime_config=config,
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
    )
