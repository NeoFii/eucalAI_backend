"""Gateway for user-service API-key validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException

from common.internal import post_internal_json

if TYPE_CHECKING:
    from core.config import RouterSettings

IDENTITY_TIMEOUT_SECONDS = 3.0
logger = logging.getLogger("router_service")


@dataclass(slots=True)
class ValidatedApiKey:
    """Minimal API-key principal returned by user-service."""

    id: int
    user_id: int
    name: str
    balance: int
    user_rpm_limit: int | None = None


class UserIdentityGateway:
    """Gateway for user-service API-key validation."""

    def __init__(self, settings: "RouterSettings") -> None:
        self._settings = settings

    async def validate_api_key(
        self,
        *,
        api_key: str,
        model: str | None = None,
        client_ip: str | None = None,
    ) -> ValidatedApiKey:
        payload = await post_internal_json(
            base_url=self._settings.USER_SERVICE_URL,
            target_service="user-service",
            path="/api/v1/internal/api-keys/validate",
            secret=self._settings.INTERNAL_SECRET,
            caller_service="router-service",
            timeout=IDENTITY_TIMEOUT_SECONDS,
            json_body={
                "key": api_key,
                "model": model,
                "client_ip": client_ip,
            },
            max_retries=self._settings.INTERNAL_HTTP_MAX_RETRIES,
            retry_backoff_seconds=self._settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
            circuit_breaker_threshold=self._settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            circuit_breaker_cooldown_seconds=self._settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )
        try:
            return ValidatedApiKey(
                id=int(payload["id"]),
                user_id=int(payload["user_id"]),
                name=payload["name"],
                balance=int(payload.get("balance", 0)),
                user_rpm_limit=payload.get("user_rpm_limit"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("malformed user-service response: %s", exc)
            raise HTTPException(
                status_code=502, detail="invalid response from user-service"
            ) from exc


__all__ = ["UserIdentityGateway", "ValidatedApiKey"]
