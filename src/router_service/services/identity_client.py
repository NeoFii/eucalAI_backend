"""Internal client for user-service API-key validation contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass

from common.internal import post_internal_json

IDENTITY_TIMEOUT_SECONDS = 3.0


@dataclass(slots=True)
class ValidatedApiKey:
    """Minimal API-key principal shared from user-service."""

    id: int
    user_id: int
    name: str


class IdentityClientService:
    """Internal client for user-service identity contracts."""

    @staticmethod
    async def validate_api_key(
        *,
        api_key: str,
        model: str | None = None,
        client_ip: str | None = None,
    ) -> ValidatedApiKey:
        payload = await post_internal_json(
            base_url=os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001"),
            target_service="user-service",
            path="/api/v1/internal/api-keys/validate",
            secret=os.getenv("INTERNAL_SECRET", ""),
            caller_service="router-service",
            timeout=IDENTITY_TIMEOUT_SECONDS,
            json_body={
                "key": api_key,
                "model": model,
                "client_ip": client_ip,
            },
            max_retries=int(os.getenv("INTERNAL_HTTP_MAX_RETRIES", "1")),
            retry_backoff_seconds=float(os.getenv("INTERNAL_HTTP_RETRY_BACKOFF_SECONDS", "0.2")),
            circuit_breaker_threshold=int(os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD", "3")),
            circuit_breaker_cooldown_seconds=float(
                os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "30.0")
            ),
        )
        return ValidatedApiKey(
            id=int(payload["id"]),
            user_id=int(payload["user_id"]),
            name=payload["name"],
        )
