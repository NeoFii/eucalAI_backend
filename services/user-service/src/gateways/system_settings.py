"""User-service gateway for admin-service system settings.

Surfaces global rate-limit settings (default RPM, system RPM cap). Cached in
Redis with a short TTL so values can be tuned at runtime by admins without
spamming admin-service.
"""

from __future__ import annotations

import logging
from typing import NoReturn

from core.config import settings
from common.cache import cache_get_or_fetch
from common.core.exceptions import (
    NotFoundException,
    ServiceUnavailableException,
    ValidationException,
)
from common.gateway.base import BaseGateway
from common.internal import (
    InternalServiceError,
    InternalServiceResponseError,
    get_internal_json,
)

logger = logging.getLogger("user_service.system_settings")

SYSTEM_SETTINGS_TIMEOUT_SECONDS = 3.0
_CACHE_PREFIX = "ss:"
_RATE_LIMITS_TTL = 60  # seconds; matches router-service config polling cadence


class SystemSettingsGateway(BaseGateway):
    """Lightweight pulls of admin-managed runtime system settings."""

    def __init__(self) -> None:
        super().__init__(service_name="admin-service")

    def _common_kwargs(self) -> dict:
        return {
            "base_url": settings.ADMIN_SERVICE_URL,
            "target_service": self.service_name,
            "secret": settings.INTERNAL_SECRET,
            "caller_service": settings.SERVICE_NAME,
            "timeout": SYSTEM_SETTINGS_TIMEOUT_SECONDS,
            "max_retries": settings.INTERNAL_HTTP_MAX_RETRIES,
            "retry_backoff_seconds": settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
            "circuit_breaker_threshold": settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            "circuit_breaker_cooldown_seconds": (
                settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
            ),
        }

    def _handle_error(self, exc: InternalServiceError) -> NoReturn:
        if isinstance(exc, InternalServiceResponseError):
            if exc.status_code == 404:
                raise NotFoundException(detail=exc.detail or "Not found") from exc
            if exc.status_code == 422:
                raise ValidationException(detail=exc.detail or "Validation error") from exc
        raise ServiceUnavailableException("System settings service unavailable") from exc

    async def _fetch_rate_limits(self) -> dict:
        """Cached fetch of rate-limit settings (used by both default RPM + cap).

        Single cache key avoids two round-trips when callers want both values.
        Returns the raw payload dict so individual getters can extract their
        field (and apply their own defaults on missing keys).
        """
        cache_key = f"{_CACHE_PREFIX}rate_limits"

        async def _fetch() -> dict:
            return await get_internal_json(
                path="/api/v1/internal/system-settings/rate-limits",
                **self._common_kwargs(),
            )

        return await cache_get_or_fetch(cache_key, _fetch, _RATE_LIMITS_TTL)

    async def get_default_user_rpm(self) -> int:
        """Return the global default per-user RPM.

        Falls back to `settings.DEFAULT_USER_RPM` (env value, default 20) if
        admin-service is unreachable — keeps user-facing screens working
        during partial outages with a slightly stale value.
        """
        try:
            payload = await self._fetch_rate_limits()
        except InternalServiceError:
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
        """Return the system-wide hard RPM cap, or None if unset/unreachable.

        Used by user/admin UIs to surface the active cap so users understand
        why their effective RPM may be lower than their configured value.
        Returns None on outage rather than guessing — UIs can simply hide the
        chip in that case.
        """
        try:
            payload = await self._fetch_rate_limits()
        except InternalServiceError:
            return None
        raw = payload.get("system_rpm_cap")
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 1 else None


__all__ = ["SystemSettingsGateway"]
