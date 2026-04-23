"""Gateway for fetching routing configuration from admin-service."""

from __future__ import annotations

import logging

from common.internal import (
    InternalCircuitOpenError,
    InternalServiceUnavailableError,
    get_internal_json,
)

logger = logging.getLogger("inference_service")


class AdminConfigGateway:
    """Fetch active routing config (inference view) from admin-service."""

    @staticmethod
    async def fetch_active_config(settings) -> dict | None:
        try:
            return await get_internal_json(
                base_url=settings.admin_service_url,
                target_service="admin-service",
                path="/api/v1/internal/routing-config/active/inference",
                secret=settings.internal_secret,
                caller_service="inference-service",
                timeout=settings.config_fetch_timeout_seconds,
                allow_404=True,
            )
        except (InternalServiceUnavailableError, InternalCircuitOpenError):
            logger.warning("admin-service unavailable, will use fallback", exc_info=True)
            return None
