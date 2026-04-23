"""Best-effort gateway for writing API call logs to user-service."""

from __future__ import annotations

import logging
from typing import Any

from common.internal import patch_internal_json, post_internal_json, InternalServiceError

logger = logging.getLogger("router_service.calllog")

_CALL_LOG_TIMEOUT = 2.0
_CALL_LOG_MAX_RETRIES = 0


class CallLogGateway:

    @staticmethod
    async def create_call_log(*, settings: Any, **fields: Any) -> dict | None:
        try:
            return await post_internal_json(
                base_url=settings.user_service_url,
                target_service="user-service",
                path="/api/v1/internal/call-logs",
                secret=settings.internal_secret,
                caller_service="router-service",
                timeout=_CALL_LOG_TIMEOUT,
                json_body=fields,
                max_retries=_CALL_LOG_MAX_RETRIES,
                circuit_breaker_threshold=0,
            )
        except Exception:
            logger.warning(
                "best-effort call log create failed for request_id=%s",
                fields.get("request_id"),
                exc_info=True,
            )
            return None

    @staticmethod
    async def update_call_log(
        *, settings: Any, request_id: str, **fields: Any
    ) -> dict | None:
        try:
            return await patch_internal_json(
                base_url=settings.user_service_url,
                target_service="user-service",
                path=f"/api/v1/internal/call-logs/{request_id}",
                secret=settings.internal_secret,
                caller_service="router-service",
                timeout=_CALL_LOG_TIMEOUT,
                json_body=fields,
                max_retries=_CALL_LOG_MAX_RETRIES,
                circuit_breaker_threshold=0,
                allow_404=True,
            )
        except Exception:
            logger.warning(
                "best-effort call log update failed for request_id=%s",
                request_id,
                exc_info=True,
            )
            return None
