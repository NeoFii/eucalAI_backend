"""Gateway contracts for router-service cross-service calls."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException

from common.gateway.base import BaseGateway
from common.internal import post_internal_json

IDENTITY_TIMEOUT_SECONDS = 3.0
logger = logging.getLogger("router_service")


@dataclass(slots=True)
class ValidatedApiKey:
    """Minimal API-key principal returned by user-service."""

    id: int
    user_id: int
    name: str
    balance: int
    rpm_limit: int | None = None


class UserIdentityGateway(BaseGateway):
    """Gateway for user-service API-key validation."""

    def __init__(self) -> None:
        super().__init__(service_name="user-service")

    @staticmethod
    async def validate_api_key(
        *,
        api_key: str,
        model: str | None = None,
        client_ip: str | None = None,
    ) -> ValidatedApiKey:
        from core.dependencies import get_settings

        settings = get_settings()
        payload = await post_internal_json(
            base_url=settings.USER_SERVICE_URL,
            target_service="user-service",
            path="/api/v1/internal/api-keys/validate",
            secret=settings.INTERNAL_SECRET,
            caller_service="router-service",
            timeout=IDENTITY_TIMEOUT_SECONDS,
            json_body={
                "key": api_key,
                "model": model,
                "client_ip": client_ip,
            },
            max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
            retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
            circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            circuit_breaker_cooldown_seconds=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )
        try:
            return ValidatedApiKey(
                id=int(payload["id"]),
                user_id=int(payload["user_id"]),
                name=payload["name"],
                balance=int(payload.get("balance", 0)),
                rpm_limit=payload.get("rpm_limit"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("malformed user-service response: %s", exc)
            raise HTTPException(
                status_code=502, detail="invalid response from user-service"
            ) from exc


__all__ = ["UserIdentityGateway", "ValidatedApiKey"]
