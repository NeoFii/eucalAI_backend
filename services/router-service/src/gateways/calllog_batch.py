"""Batch gateway for flushing buffered call logs to user-service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from common.internal import post_internal_json

if TYPE_CHECKING:
    from core.config import RouterSettings

logger = logging.getLogger("router_service.calllog_batch")

_BATCH_TIMEOUT = 10.0


class BatchCallLogGateway:

    def __init__(self, settings: "RouterSettings") -> None:
        self._settings = settings

    async def flush_batch(self, entries: list[dict]) -> bool:
        if not entries:
            return True
        try:
            await post_internal_json(
                base_url=self._settings.USER_SERVICE_URL,
                target_service="user-service",
                path="/api/v1/internal/call-logs/batch",
                secret=self._settings.INTERNAL_SECRET,
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
