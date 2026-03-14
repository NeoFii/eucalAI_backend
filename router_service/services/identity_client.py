"""Identity service client used by router service."""

from __future__ import annotations

from dataclasses import dataclass

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, get_internal_json
from router_service.config import settings

IDENTITY_TIMEOUT_SECONDS = 3.0


@dataclass
class IdentityUser:
    """Minimal user identity contract shared with router_service."""

    id: int
    uid: int
    email: str
    status: int


class IdentityClientService:
    """Internal client for the identity service."""

    @staticmethod
    async def _get(path: str) -> IdentityUser | None:
        try:
            payload = await get_internal_json(
                base_url=settings.USER_SERVICE_URL,
                target_service="user-service",
                path=path,
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=IDENTITY_TIMEOUT_SECONDS,
                allow_404=True,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("Identity service unavailable") from exc
        if payload is None:
            return None
        return IdentityUser(
            id=int(payload["id"]),
            uid=int(payload["uid"]),
            email=payload["email"],
            status=int(payload["status"]),
        )

    @staticmethod
    async def fetch_user_by_uid(uid: int) -> IdentityUser | None:
        """Look up a user by public UID via the identity service."""
        return await IdentityClientService._get(f"/api/v1/internal/users/{uid}")

    @staticmethod
    async def fetch_user_by_id(user_id: int) -> IdentityUser | None:
        """Look up a user by database id via the identity service."""
        return await IdentityClientService._get(f"/api/v1/internal/users/by-id/{user_id}")
