"""Gateway for fetching routing configuration from admin-service."""

from __future__ import annotations

import logging

from common.gateway.base import BaseGateway
from common.internal import InternalCircuitOpenError, InternalServiceUnavailableError
from inference_service.core.config import get_settings


logger = logging.getLogger("inference_service")


class AdminConfigGateway(BaseGateway):
    """Fetch active routing config (inference view) from admin-service."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            "admin-service",
            base_url=settings.ADMIN_SERVICE_URL,
            timeout=settings.CONFIG_FETCH_TIMEOUT_SECONDS,
        )

    async def fetch_active_config(self) -> dict | None:
        try:
            return await self._get(
                "/api/v1/internal/routing-config/active/inference",
                allow_404=True,
            )
        except (InternalServiceUnavailableError, InternalCircuitOpenError):
            logger.warning("admin-service unavailable, will use fallback", exc_info=True)
            return None
