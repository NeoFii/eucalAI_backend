"""Gateway for fetching routing configuration from admin-service."""

from __future__ import annotations

import logging

from common.internal import (
    InternalServiceError,
    get_internal_json,
)

logger = logging.getLogger("router_service")


class AdminConfigGateway:
    """Fetch active routing config (full view) from admin-service."""

    @staticmethod
    async def fetch_active_config(settings) -> dict | None:
        try:
            return await get_internal_json(
                base_url=settings.admin_service_url,
                target_service="admin-service",
                path="/api/v1/internal/routing-config/active/full",
                secret=settings.internal_secret,
                caller_service="router-service",
                timeout=settings.config_fetch_timeout_seconds,
                allow_404=True,
                max_retries=settings.internal_http_max_retries,
                retry_backoff_seconds=settings.internal_http_retry_backoff_seconds,
                circuit_breaker_threshold=settings.internal_http_circuit_breaker_threshold,
                circuit_breaker_cooldown_seconds=settings.internal_http_circuit_breaker_cooldown_seconds,
            )
        except InternalServiceError:
            logger.warning("failed to fetch routing config from admin-service", exc_info=True)
            return None
