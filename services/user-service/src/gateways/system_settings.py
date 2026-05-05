"""User-service gateway for admin-service system settings.

Surfaces global rate-limit settings (default RPM, system RPM cap). Cached in
Redis with a short TTL so values can be tuned at runtime by admins without
spamming admin-service.
"""

from __future__ import annotations

import logging

from common.cache import cache_get_or_fetch
from common.core.exceptions import NotFoundException, ValidationException
from common.gateway.base import BaseGateway
from common.internal import InternalServiceError
from core.config import settings

logger = logging.getLogger("user_service.system_settings")

_CACHE_PREFIX = "ss:"
_RATE_LIMITS_TTL = 60


class SystemSettingsGateway(BaseGateway):
    """Lightweight pulls of admin-managed runtime system settings."""

    def __init__(self) -> None:
        super().__init__(
            "admin-service",
            base_url=settings.ADMIN_SERVICE_URL,
            timeout=3.0,
            error_map={404: NotFoundException, 422: ValidationException},
        )

    async def _fetch_rate_limits(self) -> dict:
        cache_key = f"{_CACHE_PREFIX}rate_limits"

        async def _fetch() -> dict:
            return await self._get("/api/v1/internal/system-settings/rate-limits")

        return await cache_get_or_fetch(cache_key, _fetch, _RATE_LIMITS_TTL)

    async def get_default_user_rpm(self) -> int:
        """Return the global default per-user RPM.

        Falls back to `settings.DEFAULT_USER_RPM` if admin-service is
        unreachable — keeps user-facing screens working during partial outages.
        """
        try:
            payload = await self._fetch_rate_limits()
        except (InternalServiceError, Exception):
            logger.warning(
                "admin-service unavailable, using env DEFAULT_USER_RPM=%s as fallback",
                settings.DEFAULT_USER_RPM,
                exc_info=True,
            )
            return settings.DEFAULT_USER_RPM
        try:
            return int(payload.get("default_user_rpm", settings.DEFAULT_USER_RPM))
        except (TypeError, ValueError):
            return settings.DEFAULT_USER_RPM

    async def get_system_rpm_cap(self) -> int | None:
        """Return the system-wide hard RPM cap, or None if unset/unreachable."""
        try:
            payload = await self._fetch_rate_limits()
        except (InternalServiceError, Exception):
            return None
        raw = payload.get("system_rpm_cap")
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 1 else None


system_settings_gateway = SystemSettingsGateway()

__all__ = ["SystemSettingsGateway", "system_settings_gateway"]
