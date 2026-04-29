"""User-service gateway for admin-service model catalog.

Proxies model catalog read operations to admin-service via HMAC-signed
internal HTTP calls, with Redis (db/2) caching.
"""

from __future__ import annotations

import hashlib
from typing import NoReturn

from user_service.config import settings
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

MODEL_CATALOG_TIMEOUT_SECONDS = 5.0

_CACHE_PREFIX = "mc:"
_VENDORS_TTL = 300
_CATEGORIES_TTL = 300
_MODELS_LIST_TTL = 120
_MODEL_DETAIL_TTL = 300


class ModelCatalogGateway(BaseGateway):
    """HTTP gateway for model catalog data from admin-service."""

    def __init__(self) -> None:
        super().__init__(service_name="admin-service")

    def _common_kwargs(self) -> dict:
        return {
            "base_url": settings.ADMIN_SERVICE_URL,
            "target_service": self.service_name,
            "secret": settings.INTERNAL_SECRET,
            "caller_service": settings.SERVICE_NAME,
            "timeout": MODEL_CATALOG_TIMEOUT_SECONDS,
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
        raise ServiceUnavailableException("Model catalog service unavailable") from exc

    async def list_vendors(self, *, page: int = 1, page_size: int = 100) -> dict:
        cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

        async def _fetch() -> dict:
            return await get_internal_json(
                path="/api/v1/internal/model-catalog/vendors",
                query_params={"page": page, "page_size": page_size},
                **self._common_kwargs(),
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_categories(self, *, page: int = 1, page_size: int = 100) -> dict:
        cache_key = f"{_CACHE_PREFIX}categories:{page}:{page_size}"

        async def _fetch() -> dict:
            return await get_internal_json(
                path="/api/v1/internal/model-catalog/categories",
                query_params={"page": page, "page_size": page_size},
                **self._common_kwargs(),
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _CATEGORIES_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_models(
        self,
        *,
        category: str | None = None,
        vendors: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        qp: dict = {"page": page, "page_size": page_size}
        if category:
            qp["category"] = category
        if vendors:
            qp["vendors"] = vendors
        if q:
            qp["q"] = q
        params_str = "&".join(f"{k}={v}" for k, v in sorted(qp.items()))
        cache_key = f"{_CACHE_PREFIX}models:{hashlib.sha256(params_str.encode()).hexdigest()[:16]}"

        async def _fetch() -> dict:
            return await get_internal_json(
                path="/api/v1/internal/model-catalog/models",
                query_params=qp,
                **self._common_kwargs(),
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _MODELS_LIST_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_model(self, slug: str) -> dict:
        cache_key = f"{_CACHE_PREFIX}model:{slug}"

        async def _fetch() -> dict:
            return await get_internal_json(
                path=f"/api/v1/internal/model-catalog/models/{slug}",
                **self._common_kwargs(),
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _MODEL_DETAIL_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)
