"""Batch gateway for flushing buffered call logs to user-service."""

from __future__ import annotations

import logging
from typing import Any

from common.internal import post_internal_json

logger = logging.getLogger("router_service.calllog_batch")

_BATCH_TIMEOUT = 10.0


class BatchCallLogGateway:

    @staticmethod
    async def flush_batch(*, settings: Any, entries: list[dict]) -> bool:
        if not entries:
            return True
        try:
            await post_internal_json(
                base_url=settings.user_service_url,
                target_service="user-service",
                path="/api/v1/internal/call-logs/batch",
                secret=settings.internal_secret,
                caller_service="router-service",
                timeout=_BATCH_TIMEOUT,
                json_body={"entries": entries},
                max_retries=0,
                circuit_breaker_threshold=0,
            )
            logger.debug("flushed %d call-log entries", len(entries))
            return True
        except Exception:
            logger.warning("batch call-log flush failed (%d entries)", len(entries), exc_info=True)
            return False
