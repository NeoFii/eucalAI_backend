"""Gateways for admin-service external contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod

from admin_service.config import settings
from common.core.exceptions import ServiceUnavailableException
from common.gateway.base import BaseGateway
from common.internal import InternalServiceError, get_internal_json

IDENTITY_TIMEOUT_SECONDS = 3.0


class UserStatsGatewayInterface(ABC):
    """Contract for user-service statistics needed by admin-service."""

    @abstractmethod
    async def fetch_total_users(self) -> int:
        """Return the total user count."""


class UserStatsGateway(BaseGateway, UserStatsGatewayInterface):
    """HTTP gateway for user-service statistics."""

    def __init__(self) -> None:
        super().__init__(service_name="user-service")

    async def fetch_total_users(self) -> int:
        try:
            payload = await get_internal_json(
                base_url=settings.USER_SERVICE_URL,
                target_service=self.service_name,
                path="/api/v1/internal/stats/users",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=IDENTITY_TIMEOUT_SECONDS,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("User identity service unavailable") from exc
        return int(payload["total_users"])
