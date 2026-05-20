"""User-facing model catalog read service.

Composed of two source analogs (per 04-PATTERNS § services/model_catalog_service.py):

1. Cache scaffolding from ``services/user-service/src/gateways/model_catalog.py``
   (constants + ``cache_get_or_fetch`` wrapping; ``mc:`` key prefix and the four
   source TTLs are locked at lines 17-21 of the gateway).
2. Read methods from the admin domain's existing model catalog service
   (``_vendor_item`` / ``_category_item`` / ``_model_item`` serializers plus
   ``list_vendors`` / ``list_categories`` / ``list_models`` / ``get_model_by_slug``).

The out-of-process gateway pattern that the user-service used to reach the
admin domain for catalog data is replaced here by direct, in-process
repository calls — one fewer network hop per request. The Phase 3
``ModelCatalogRepository`` already eager-loads the ``vendor`` and
``category_links`` relationships, so the serializer never triggers a lazy
fetch.

Class name is **ModelCatalogReadService** (D-07): the bare
``ModelCatalogService`` symbol stays free for the Phase 5 admin write variant
that will live alongside this one.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import NotFoundException
from app.common.infra.cache import cache_get_or_fetch
from app.model import ModelCatalog, ModelCategory, ModelVendor
from app.repository.model_catalog_repository import (
    ModelCatalogRepository,
    ModelCategoryRepository,
    ModelVendorRepository,
)
from app.schema.model_catalog import (
    ModelCategoryBrief,
    ModelCategoryItem,
    ModelVendorBrief,
    ModelVendorItem,
    SupportedModelDetail,
    SupportedModelItem,
)

logger = logging.getLogger(__name__)


# Cache layout — keys and TTLs locked to the source gateway
# (services/user-service/src/gateways/model_catalog.py:17-21).
_CACHE_PREFIX = "mc:"
_VENDORS_TTL = 300
_CATEGORIES_TTL = 300
_MODELS_LIST_TTL = 120
_MODEL_DETAIL_TTL = 300

# TODO(phase-5): admin writes invalidate mc:* keys (D-05 — currently
# correct-up-to-TTL; cache only grows in Phase 4).


def _filter_hash(*, page: int, page_size: int, vendors: list[str] | None,
                 q: str | None, category: str | None) -> str:
    """Stable 12-char digest for the /models filter set — bounds cache-key cardinality."""
    payload = json.dumps(
        {
            "page": page,
            "page_size": page_size,
            "vendors": sorted(vendors) if vendors else None,
            "q": q,
            "category": category,
        },
        sort_keys=True,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]


class ModelCatalogReadService:
    """Read-only public catalog access with Redis caching (mc:* keys)."""

    # ── Serializers (port of the admin domain catalog item builders) ──

    @staticmethod
    def _vendor_item(vendor: ModelVendor) -> ModelVendorItem:
        return ModelVendorItem(
            id=vendor.id,
            slug=vendor.slug,
            name=vendor.name,
            logo_url=vendor.logo_url,
            is_active=vendor.is_active,
            sort_order=vendor.sort_order,
            created_at=vendor.created_at,
            updated_at=vendor.updated_at,
        )

    @staticmethod
    def _category_item(category: ModelCategory) -> ModelCategoryItem:
        return ModelCategoryItem(
            id=category.id,
            key=category.key,
            name=category.name,
            sort_order=category.sort_order,
            is_active=category.is_active,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    @staticmethod
    def _model_item(
        model: ModelCatalog,
        *,
        detail: bool = False,
    ) -> SupportedModelItem | SupportedModelDetail:
        categories = [
            ModelCategoryBrief(
                key=link.category.key,
                name=link.category.name,
                sort_order=link.sort_order,
            )
            for link in sorted(model.category_links, key=lambda item: item.sort_order)
            if link.category is not None
        ]
        payload = {
            "id": model.id,
            "slug": model.slug,
            "routing_slug": model.routing_slug,
            "name": model.name,
            "summary": model.summary,
            "description": model.description,
            "sale_input_per_million": model.sale_input_per_million,
            "sale_output_per_million": model.sale_output_per_million,
            "sale_cached_input_per_million": model.sale_cached_input_per_million,
            "capability_tags": list(model.capability_tags or []),
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "is_reasoning_model": model.is_reasoning_model,
            "is_active": model.is_active,
            "sort_order": model.sort_order,
            "vendor": ModelVendorBrief(
                id=model.vendor.id,
                slug=model.vendor.slug,
                name=model.vendor.name,
                logo_url=model.vendor.logo_url,
            ),
            "categories": categories,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
        if detail:
            return SupportedModelDetail(**payload)
        return SupportedModelItem(**payload)

    # ── Public read methods ──────────────────────────────────────────────────

    @staticmethod
    async def list_vendors(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

        async def _fetch() -> dict:
            # D-04: user surface always filters to active vendors.
            vendors, total = await ModelVendorRepository(db).list_vendors(
                page=page,
                page_size=page_size,
                active_only=True,
            )
            items = [
                ModelCatalogReadService._vendor_item(vendor).model_dump()
                for vendor in vendors
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

        return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)

    @staticmethod
    async def list_categories(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        cache_key = f"{_CACHE_PREFIX}categories:{page}:{page_size}"

        async def _fetch() -> dict:
            # D-04: user surface always filters to active categories.
            categories, total = await ModelCategoryRepository(db).list_categories(
                page=page,
                page_size=page_size,
                active_only=True,
            )
            items = [
                ModelCatalogReadService._category_item(category).model_dump()
                for category in categories
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

        return await cache_get_or_fetch(cache_key, _fetch, _CATEGORIES_TTL)

    @staticmethod
    async def list_models(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 50,
        vendors: list[str] | None = None,
        q: str | None = None,
        category: str | None = None,
    ) -> dict:
        digest = _filter_hash(
            page=page,
            page_size=page_size,
            vendors=vendors,
            q=q,
            category=category,
        )
        cache_key = f"{_CACHE_PREFIX}models:{digest}"

        async def _fetch() -> dict:
            # D-04: user surface always filters to active models / active vendors.
            models, total = await ModelCatalogRepository(db).list_models(
                page=page,
                page_size=page_size,
                vendors=vendors,
                q=q,
                category=category,
                active_only=True,
            )
            items = [
                ModelCatalogReadService._model_item(model).model_dump()
                for model in models
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

        return await cache_get_or_fetch(cache_key, _fetch, _MODELS_LIST_TTL)

    @staticmethod
    async def get_model_by_slug(db: AsyncSession, slug: str) -> dict:
        cache_key = f"{_CACHE_PREFIX}model:{slug}"

        async def _fetch() -> dict:
            # D-04: user surface always filters to active.
            model = await ModelCatalogRepository(db).get_by_slug(slug, active_only=True)
            if model is None:
                raise NotFoundException(detail=f"Model not found: {slug}")
            return ModelCatalogReadService._model_item(model, detail=True).model_dump()

        return await cache_get_or_fetch(cache_key, _fetch, _MODEL_DETAIL_TTL)


__all__ = [
    "ModelCatalogReadService",
    "_CACHE_PREFIX",
    "_CATEGORIES_TTL",
    "_MODELS_LIST_TTL",
    "_MODEL_DETAIL_TTL",
    "_VENDORS_TTL",
]
