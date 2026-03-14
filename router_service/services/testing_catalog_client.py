"""Client for testing-service router catalog contracts."""

from __future__ import annotations

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, get_internal_json, post_internal_json
from router_service.config import settings

CATALOG_TIMEOUT_SECONDS = 5.0


class TestingCatalogClientService:
    """Consume testing-service router catalog internal APIs."""

    @staticmethod
    async def list_models() -> dict:
        try:
            return await get_internal_json(
                base_url=settings.TESTING_SERVICE_URL,
                target_service="testing-service",
                path="/api/v1/internal/router/models",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=CATALOG_TIMEOUT_SECONDS,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("Testing catalog service unavailable") from exc

    @staticmethod
    async def resolve_routes(*, model_name: str, provider_hint: str | None = None) -> dict:
        try:
            return await post_internal_json(
                base_url=settings.TESTING_SERVICE_URL,
                target_service="testing-service",
                path="/api/v1/internal/router/routes/resolve",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=CATALOG_TIMEOUT_SECONDS,
                json_body={"model_name": model_name, "provider_hint": provider_hint},
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("Testing catalog service unavailable") from exc

    @staticmethod
    async def get_offering(offering_id: int) -> dict | None:
        try:
            return await get_internal_json(
                base_url=settings.TESTING_SERVICE_URL,
                target_service="testing-service",
                path=f"/api/v1/internal/router/offerings/{offering_id}",
                secret=settings.INTERNAL_SECRET,
                caller_service=settings.SERVICE_NAME,
                timeout=CATALOG_TIMEOUT_SECONDS,
                allow_404=True,
                max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
                retry_backoff_seconds=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
                circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
                circuit_breaker_cooldown_seconds=(
                    settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                ),
            )
        except InternalServiceError as exc:
            raise ServiceUnavailableException("Testing catalog service unavailable") from exc
