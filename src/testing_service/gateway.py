"""Gateway contracts for testing-service cross-service calls."""

from __future__ import annotations

from dataclasses import dataclass

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, get_internal_json
from testing_service.config import get_settings

IDENTITY_TIMEOUT_SECONDS = 3.0


@dataclass(slots=True)
class AdminIdentity:
    """Minimal admin identity contract shared with testing_service."""

    id: int
    uid: int
    email: str
    name: str
    role: str
    status: int


class AdminIdentityGateway:
    """Gateway for the admin identity contract exposed by admin-service."""

    @staticmethod
    async def fetch_admin_by_uid(uid: int) -> AdminIdentity | None:
        """Look up an admin by public uid via the admin service."""
        settings = get_settings()
        try:
            payload = await get_internal_json(
                base_url=settings.admin_service_url,
                target_service="admin-service",
                path=f"/api/v1/internal/admins/{uid}",
                secret=settings.internal_secret,
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

__all__ = ["AdminIdentity", "AdminIdentityGateway"]
