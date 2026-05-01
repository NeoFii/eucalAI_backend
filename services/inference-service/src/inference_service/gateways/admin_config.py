"""Gateway for fetching routing configuration from admin-service."""

from __future__ import annotations

import logging
from typing import Any

from common.gateway.base import BaseGateway
from common.internal import (
    InternalCircuitOpenError,
    InternalServiceUnavailableError,
    get_internal_json,
)

logger = logging.getLogger("inference_service")


class AdminConfigGateway(BaseGateway):
    """Fetch active routing config (inference view) from admin-service."""

    def __init__(self) -> None:
        super().__init__(service_name="admin-service")

    @staticmethod
    async def fetch_active_config(settings: Any) -> dict | None:
        try:
            return await get_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service="admin-service",
                path="/api/v1/internal/routing-config/active/inference",
                secret=settings.INTERNAL_SECRET,
                caller_service="inference-service",
                timeout=settings.CONFIG_FETCH_TIMEOUT_SECONDS,
                allow_404=True,
            )
        except (InternalServiceUnavailableError, InternalCircuitOpenError):
            logger.warning("admin-service unavailable, will use fallback", exc_info=True)
            return None
