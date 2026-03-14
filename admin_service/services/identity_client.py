"""Identity client used by admin control-plane endpoints."""

from __future__ import annotations

from common.core.exceptions import ServiceUnavailableException
from admin_service.config import settings
from common.internal import InternalServiceError, get_internal_json

IDENTITY_TIMEOUT_SECONDS = 3.0


class IdentityClientService:
    """Internal client for identity-service contracts."""

    @staticmethod
    async def fetch_total_users() -> int:
        """Fetch the total user count from the identity service."""
        try:
            payload = await get_internal_json(
                base_url=settings.USER_SERVICE_URL,
                target_service="user-service",
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
