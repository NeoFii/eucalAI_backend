"""Gateway for fetching routing configuration from admin-service."""

from __future__ import annotations

import logging

from common.internal import (
    InternalCircuitOpenError,
    InternalServiceUnavailableError,
    get_internal_json,
)

logger = logging.getLogger("router_service")


class AdminConfigGateway:
    """Fetch active routing config (full view) from admin-service."""

    @staticmethod
    async def fetch_active_config(settings) -> dict | None:
        try:
            return await get_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service="admin-service",
                path="/api/v1/internal/routing-config/active/full",
                secret=settings.INTERNAL_SECRET,
                caller_service="router-service",
                timeout=settings.CONFIG_FETCH_TIMEOUT_SECONDS,
                allow_404=True,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
            )
        except (InternalServiceUnavailableError, InternalCircuitOpenError):
            logger.warning("admin-service unavailable, will use fallback", exc_info=True)
            return None
