"""ClassifyService: orchestrates engine + config_manager for classification."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from common.observability import get_request_id
from inference_service.schemas.classify import ClassifyResponse

if TYPE_CHECKING:
    from inference_service.schemas.classify import ClassifyRequest
    from inference_service.services.config_manager import ConfigManager
    from inference_service.services.router_engine import HybridIntegratedDifficultyRouter

logger = logging.getLogger("inference_service")

CLASSIFY_SOFT_TIMEOUT_SECONDS = 30.0


class ClassifyService:
    _gpu_semaphore: asyncio.Semaphore | None = None

    @classmethod
    def init_semaphore(cls, limit: int) -> None:
        cls._gpu_semaphore = asyncio.Semaphore(limit)

    @staticmethod
    async def classify(
        request: ClassifyRequest,
        engine: HybridIntegratedDifficultyRouter,
        config_manager: ConfigManager,
    ) -> ClassifyResponse:
        config = config_manager.load()
        config_version = config_manager.config_version
        config_source = config_manager.config_source

        request_id = get_request_id() or request.request_id or ""

        sem = ClassifyService._gpu_semaphore
        if sem is not None:
            await sem.acquire()
        try:
            t_start = time.monotonic()
            result = await asyncio.to_thread(
                engine.predict_chat_messages,
                request.messages,
                request_id=request_id,
                runtime_config=config,
            )
            elapsed = time.monotonic() - t_start
        finally:
            if sem is not None:
                sem.release()

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
