"""Internal admin identity client used by the content service."""

from __future__ import annotations

from dataclasses import dataclass

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, get_internal_json
from content_service.config import settings

IDENTITY_TIMEOUT_SECONDS = 3.0


@dataclass(slots=True)
class AdminIdentity:
    """Minimal admin identity contract for content-service."""

    id: int
    uid: int
    email: str
    name: str
    role: str
    status: int


class AdminIdentityClientService:
    """Resolve admin principals through admin-service internal APIs."""

    @staticmethod
    async def fetch_admin_by_uid(uid: int) -> AdminIdentity | None:
        try:
            payload = await get_internal_json(
                base_url=settings.ADMIN_SERVICE_URL,
                target_service="admin-service",
                path=f"/api/v1/internal/admins/{uid}",
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
            raise ServiceUnavailableException("Admin identity service unavailable") from exc
        if payload is None:
            return None
        return AdminIdentity(
            id=int(payload["id"]),
            uid=int(payload["uid"]),
            email=payload["email"],
            name=payload["name"],
            role=payload["role"],
            status=int(payload["status"]),
        )
