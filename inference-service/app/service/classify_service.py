"""ClassifyService: orchestrates engine + config_manager for classification."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.common.observability import get_request_id, log_event
from app.schema.classify import ClassifyResponse

if TYPE_CHECKING:
    from app.schema.classify import ClassifyRequest
    from app.service.config_manager import ConfigManager
    from app.service.router_engine import HybridIntegratedDifficultyRouter

logger = logging.getLogger("inference_service")

CLASSIFY_SOFT_TIMEOUT_SECONDS = 30.0

_gpu_semaphore: asyncio.Semaphore | None = None


def init_gpu_semaphore(limit: int) -> None:
    global _gpu_semaphore
    _gpu_semaphore = asyncio.Semaphore(limit)


class ClassifyService:

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
        messages_count = len(request.messages)

        queued_ms = 0.0
        if _gpu_semaphore is not None:
            t_queue = time.monotonic()
            await _gpu_semaphore.acquire()
            queued_ms = round((time.monotonic() - t_queue) * 1000, 2)
        try:
            t_start = time.monotonic()
            try:
                result = await asyncio.to_thread(
                    engine.predict_chat_messages,
                    request.messages,
                    request_id=request_id,
                    runtime_config=config,
                )
            except Exception as exc:
                engine_latency_ms = round((time.monotonic() - t_start) * 1000, 2)
                log_event(
                    logger, logging.ERROR, "classifyFailed",
                    requestId=request_id,
                    messagesCount=messages_count,
                    queuedMs=queued_ms,
                    engineLatencyMs=engine_latency_ms,
                    errorCode=type(exc).__name__,
                    errorDetail=str(exc)[:256],
                    configVersion=config_version,
                    configSource=config_source,
                )
                raise
            elapsed = time.monotonic() - t_start
        finally:
            if _gpu_semaphore is not None:
                _gpu_semaphore.release()

        latency_ms = round(elapsed * 1000, 2)
        soft_timeout = elapsed > CLASSIFY_SOFT_TIMEOUT_SECONDS

        log_event(
            logger, logging.INFO, "classifyComplete",
            requestId=request_id,
            messagesCount=messages_count,
            queuedMs=queued_ms,
            engineLatencyMs=latency_ms,
            routingTier=result["routing_tier"],
            selectedModel=result["selected_model"],
            totalScore=result["total_score_0_10"],
            scoreSource=result["score_source"],
            protoWeighted_0_2=result.get("proto_weighted_0_2"),
            softTimeout=soft_timeout,
            configVersion=config_version,
            configSource=config_source,
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
