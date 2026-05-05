"""User-service gateway for admin-service model catalog.

Proxies model catalog read operations to admin-service via HMAC-signed
internal HTTP calls, with Redis (db/2) caching.
"""

from __future__ import annotations

import hashlib

from common.cache import cache_get_or_fetch
from common.core.exceptions import NotFoundException, ValidationException
from common.gateway.base import BaseGateway
from common.internal import InternalServiceError
from core.config import settings

_CACHE_PREFIX = "mc:"
_VENDORS_TTL = 300
_CATEGORIES_TTL = 300
_MODELS_LIST_TTL = 120
_MODEL_DETAIL_TTL = 300


class ModelCatalogGateway(BaseGateway):
    """HTTP gateway for model catalog data from admin-service."""

    def __init__(self) -> None:
        super().__init__(
            "admin-service",
            base_url=settings.ADMIN_SERVICE_URL,
            timeout=5.0,
            error_map={404: NotFoundException, 422: ValidationException},
        )

    async def list_vendors(self, *, page: int = 1, page_size: int = 100) -> dict:
        cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

        async def _fetch() -> dict:
            return await self._get(
                "/api/v1/internal/model-catalog/vendors",
                query_params={"page": page, "page_size": page_size},
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def list_categories(self, *, page: int = 1, page_size: int = 100) -> dict:
        cache_key = f"{_CACHE_PREFIX}categories:{page}:{page_size}"

        async def _fetch() -> dict:
            return await self._get(
                "/api/v1/internal/model-catalog/categories",
                query_params={"page": page, "page_size": page_size},
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
        cache_key = (
            f"{_CACHE_PREFIX}models:{hashlib.sha256(params_str.encode()).hexdigest()[:16]}"
        )

        async def _fetch() -> dict:
            return await self._get(
                "/api/v1/internal/model-catalog/models",
                query_params=qp,
            )

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _MODELS_LIST_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)

    async def get_model(self, slug: str) -> dict:
        cache_key = f"{_CACHE_PREFIX}model:{slug}"

        async def _fetch() -> dict:
            return await self._get(f"/api/v1/internal/model-catalog/models/{slug}")

        try:
            return await cache_get_or_fetch(cache_key, _fetch, _MODEL_DETAIL_TTL)
        except InternalServiceError as exc:
            self._handle_error(exc)


model_catalog_gateway = ModelCatalogGateway()

__all__ = ["ModelCatalogGateway", "model_catalog_gateway"]
