"""Admin model catalog service (vendor / category / model CRUD).

Ported verbatim from `services/admin-service/src/services/model_catalog_service.py`
in Plan 05-02 / Task 2, with the following rewrites:

- Model rename: `SupportedModel` → `ModelCatalog` (Phase 3 renamed the table
  and ORM class). All in-file references updated.
- Model rename: `SupportedModelCategoryMap` → `ModelCatalogCategoryMap`.
- Repository rename: `SupportedModelRepository` → `ModelCatalogRepository`.
- Standard import rewrites (`from models` → `from api_service.models`,
  `from repositories` → `from api_service.repositories.model_catalog_repository`,
  `from services.audit_service` → `from api_service.services.admin.audit_service`,
  `from schemas.model_catalog` → `from api_service.schemas.admin.model_catalog`,
  `from common.core.exceptions` → `from api_service.common.core.exceptions`).

D-05 (NEW): every successful write method calls
`await ModelCatalogService._invalidate_cache()` AFTER `await db.commit()`.
The helper performs a fail-open SCAN+DEL of all `mc:*` cache keys (Redis
db/2). Failure to invalidate is logged but does not roll back the
business mutation (the cache TTL of <= 300s is the safety net).

`AdminConflictException` (HTTP 409) is raised on duplicate slug/key on
create operations (Pitfall 15 + the plan acceptance criterion that uses
the admin-grade conflict class instead of the generic `ValidationException`).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
    AdminConflictException,
    NotFoundException,
    ValidationException,
)
from api_service.common.infra.cache import get_cache_redis
from api_service.models import (
    ModelCatalog,
    ModelCatalogCategoryMap,
    ModelCategory,
    ModelVendor,
)
from api_service.repositories.model_catalog_repository import (
    ModelCatalogRepository,
    ModelCategoryRepository,
    ModelVendorRepository,
)
from api_service.schemas.admin.model_catalog import (
    ModelCategoryBrief,
    ModelCategoryCreate,
    ModelCategoryItem,
    ModelCategoryUpdate,
    ModelVendorBrief,
    ModelVendorCreate,
    ModelVendorItem,
    ModelVendorUpdate,
    SupportedModelCreate,
    SupportedModelDetail,
    SupportedModelItem,
    SupportedModelUpdate,
)
from api_service.services.admin.audit_service import AdminAuditService

logger = logging.getLogger(__name__)


class ModelCatalogService:
    """Read and mutate the model catalog (admin domain)."""

    # ------------------------------------------------------------------
    # D-05: cache invalidation (mc:* SCAN + DEL, fail-open)
    # ------------------------------------------------------------------

    @staticmethod
    async def _invalidate_cache() -> None:
        """Invalidate all `mc:*` cache keys (Redis db/2) after every
        successful write (D-05).

        Fail-open: any exception is logged but does not propagate.  The
        cache TTL acts as the safety net so admin writes never get rolled
        back due to Redis being unavailable.  Post-commit ordering is
        deliberate (Phase 5 CONTEXT specifics line 259): rolling back a
        mutation should NOT clear the cache.
        """
        try:
            r = get_cache_redis()
            async for key in r.scan_iter(match="mc:*"):
                await r.delete(key)
        except Exception:
            logger.warning(
                "model_catalog cache invalidation failed", exc_info=True,
            )

    # ------------------------------------------------------------------
    # Serializers
    # ------------------------------------------------------------------

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
    def _model_item(model: ModelCatalog, *, detail: bool = False) -> SupportedModelItem:
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
        }
        if detail:
            return SupportedModelDetail(**payload)
        return SupportedModelItem(**payload)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    async def list_vendors(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
        active_only: bool = True,
    ) -> tuple[list[ModelVendorItem], int]:
        vendors, total = await ModelVendorRepository(db).list_vendors(
            page=page, page_size=page_size, active_only=active_only,
        )
        return [ModelCatalogService._vendor_item(v) for v in vendors], total

    @staticmethod
    async def list_categories(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
        active_only: bool = True,
    ) -> tuple[list[ModelCategoryItem], int]:
        categories, total = await ModelCategoryRepository(db).list_categories(
            page=page, page_size=page_size, active_only=active_only,
        )
        return [ModelCatalogService._category_item(c) for c in categories], total

    @staticmethod
    async def list_models(
        db: AsyncSession,
        *,
        category: str | None = None,
        vendors: list[str] | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = True,
        status: str | None = None,
    ) -> tuple[list[SupportedModelItem], int]:
        models, total = await ModelCatalogRepository(db).list_models(
            page=page, page_size=page_size, active_only=active_only,
            status=status, category=category, vendors=vendors, q=q,
        )
        return [ModelCatalogService._model_item(m) for m in models], total

    @staticmethod
    async def get_model_by_slug(
        db: AsyncSession, slug: str, *, active_only: bool = True,
    ) -> SupportedModelDetail:
        model = await ModelCatalogRepository(db).get_by_slug(slug, active_only=active_only)
        if model is None:
            raise NotFoundException("model not found")
        return ModelCatalogService._model_item(model, detail=True)

    # ------------------------------------------------------------------
    # Vendor mutations
    # ------------------------------------------------------------------

    @staticmethod
    async def create_vendor(
        db: AsyncSession,
        payload: ModelVendorCreate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ModelVendorItem:
        repo = ModelVendorRepository(db)
        if await repo.get_by_slug(payload.slug):
            raise AdminConflictException("vendor slug already exists")
        vendor = ModelVendor(**payload.model_dump())
        repo.add(vendor)
        if actor_admin_id is not None:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="create_model_vendor",
                resource_type="model_vendor",
                resource_id=payload.slug,
                status="success",
                after_data=payload.model_dump(),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        await db.refresh(vendor)
        return ModelCatalogService._vendor_item(vendor)

    @staticmethod
    async def update_vendor(
        db: AsyncSession,
        slug: str,
        payload: ModelVendorUpdate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ModelVendorItem:
        vendor = await ModelVendorRepository(db).get_by_slug(slug)
        if vendor is None:
            raise NotFoundException("vendor not found")
        changed = payload.model_dump(exclude_unset=True)
        for key, value in changed.items():
            setattr(vendor, key, value)
        if actor_admin_id is not None and changed:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="update_model_vendor",
                resource_type="model_vendor",
                resource_id=slug,
                status="success",
                after_data=changed,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        await db.refresh(vendor)
        return ModelCatalogService._vendor_item(vendor)

    # ------------------------------------------------------------------
    # Category mutations
    # ------------------------------------------------------------------

    @staticmethod
    async def create_category(
        db: AsyncSession,
        payload: ModelCategoryCreate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ModelCategoryItem:
        repo = ModelCategoryRepository(db)
        if await repo.get_by_key(payload.key):
            raise AdminConflictException("category key already exists")
        category = ModelCategory(**payload.model_dump())
        repo.add(category)
        if actor_admin_id is not None:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="create_model_category",
                resource_type="model_category",
                resource_id=payload.key,
                status="success",
                after_data=payload.model_dump(),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        await db.refresh(category)
        return ModelCatalogService._category_item(category)

    @staticmethod
    async def update_category(
        db: AsyncSession,
        key: str,
        payload: ModelCategoryUpdate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ModelCategoryItem:
        category = await ModelCategoryRepository(db).get_by_key(key)
        if category is None:
            raise NotFoundException("category not found")
        changed = payload.model_dump(exclude_unset=True)
        for field, value in changed.items():
            setattr(category, field, value)
        if actor_admin_id is not None and changed:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="update_model_category",
                resource_type="model_category",
                resource_id=key,
                status="success",
                after_data=changed,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        await db.refresh(category)
        return ModelCatalogService._category_item(category)

    # ------------------------------------------------------------------
    # Model mutations
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_vendor(db: AsyncSession, slug: str) -> ModelVendor:
        vendor = await ModelVendorRepository(db).get_by_slug(slug)
        if vendor is None:
            raise NotFoundException("vendor not found")
        return vendor

    @staticmethod
    async def _resolve_categories(
        db: AsyncSession, keys: list[str],
    ) -> list[ModelCategory]:
        if not keys:
            return []
        category_repo = ModelCategoryRepository(db)
        categories: list[ModelCategory] = []
        missing: list[str] = []
        for key in keys:
            category = await category_repo.get_by_key(key)
            if category is None:
                missing.append(key)
            else:
                categories.append(category)
        if missing:
            raise NotFoundException(f"categories not found: {', '.join(missing)}")
        return categories

    @staticmethod
    def _replace_categories(
        model: ModelCatalog, categories: list[ModelCategory],
    ) -> None:
        existing_by_category_id: dict[int, ModelCatalogCategoryMap] = {}
        for link in model.category_links:
            category_id = link.category_id or (link.category.id if link.category else None)
            if category_id is not None:
                existing_by_category_id[category_id] = link

        next_links: list[ModelCatalogCategoryMap] = []
        for index, category in enumerate(categories):
            category_id = category.id
            link = (
                existing_by_category_id.get(category_id)
                if category_id is not None
                else None
            )
            if link is None:
                link = ModelCatalogCategoryMap(category=category, category_id=category_id)
            else:
                link.category = category
                link.category_id = category_id
            link.sort_order = index + 1
            next_links.append(link)

        model.category_links = next_links

    @staticmethod
    async def create_model(
        db: AsyncSession,
        payload: SupportedModelCreate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SupportedModelDetail:
        model_repo = ModelCatalogRepository(db)
        if await model_repo.get_by_slug(payload.slug, active_only=False):
            raise AdminConflictException("model slug already exists")

        if payload.is_active:
            if not payload.routing_slug or not payload.routing_slug.strip():
                raise ValidationException("活跃模型必须设置路由标识（routing_slug）")
            if payload.sale_input_per_million is None or payload.sale_output_per_million is None:
                raise ValidationException("活跃模型必须设置输入和输出定价")

        vendor = await ModelCatalogService._resolve_vendor(db, payload.vendor_slug)
        categories = await ModelCatalogService._resolve_categories(db, payload.category_keys)
        model = ModelCatalog(
            slug=payload.slug,
            routing_slug=payload.routing_slug,
            name=payload.name,
            vendor=vendor,
            summary=payload.summary,
            description=payload.description,
            sale_input_per_million=payload.sale_input_per_million,
            sale_output_per_million=payload.sale_output_per_million,
            sale_cached_input_per_million=payload.sale_cached_input_per_million,
            capability_tags=payload.capability_tags,
            context_window=payload.context_window,
            max_output_tokens=payload.max_output_tokens,
            is_reasoning_model=payload.is_reasoning_model,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        ModelCatalogService._replace_categories(model, categories)
        model_repo.add(model)
        if actor_admin_id is not None:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="create_supported_model",
                resource_type="supported_model",
                resource_id=payload.slug,
                status="success",
                after_data=payload.model_dump(),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        return await ModelCatalogService.get_model_by_slug(db, payload.slug, active_only=False)

    @staticmethod
    async def update_model(
        db: AsyncSession,
        slug: str,
        payload: SupportedModelUpdate,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SupportedModelDetail:
        model_repo = ModelCatalogRepository(db)
        model = await model_repo.get_by_slug(slug, active_only=False)
        if model is None:
            raise NotFoundException("model not found")

        data = payload.model_dump(exclude_unset=True)
        if "routing_slug" in data:
            new_routing_slug = data["routing_slug"]
            old_routing_slug = model.routing_slug
            if old_routing_slug and (not new_routing_slug or not str(new_routing_slug).strip()):
                from api_service.repositories.routing_setting_repository import (
                    RoutingSettingRepository,
                )
                referencing_tiers = await RoutingSettingRepository(db).get_tier_keys_by_model_slug(
                    old_routing_slug
                )
                if referencing_tiers:
                    tier_list = ", ".join(referencing_tiers)
                    raise ValidationException(
                        f"无法清空路由标识：当前值 '{old_routing_slug}' "
                        f"正被路由配置 [{tier_list}] 引用，"
                        f"请先在路由设置中更换对应层级的模型"
                    )
        if "vendor_slug" in data:
            model.vendor = await ModelCatalogService._resolve_vendor(db, data.pop("vendor_slug"))
        if "category_keys" in data:
            categories = await ModelCatalogService._resolve_categories(
                db, data.pop("category_keys"),
            )
            ModelCatalogService._replace_categories(model, categories)
        for field, value in data.items():
            setattr(model, field, value)
        if actor_admin_id is not None:
            changed = payload.model_dump(exclude_unset=True)
            if changed:
                await AdminAuditService.record(
                    db,
                    actor_admin_id=actor_admin_id,
                    target_admin_id=None,
                    action="update_supported_model",
                    resource_type="supported_model",
                    resource_id=slug,
                    status="success",
                    after_data=changed,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        await db.commit()
        await ModelCatalogService._invalidate_cache()
        return await ModelCatalogService.get_model_by_slug(db, slug, active_only=False)

    @staticmethod
    async def disable_model(
        db: AsyncSession,
        slug: str,
        *,
        actor_admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """归档模型（软删除）：is_active=False，记录留存便于后续恢复或审计。"""
        model = await ModelCatalogRepository(db).get_by_slug(slug, active_only=False)
        if model is None:
            raise NotFoundException("model not found")
        model.is_active = False
        if actor_admin_id is not None:
            await AdminAuditService.record(
                db,
                actor_admin_id=actor_admin_id,
                target_admin_id=None,
                action="archive_supported_model",
                resource_type="supported_model",
                resource_id=slug,
                status="success",
                after_data={"is_active": False},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await db.commit()
        await ModelCatalogService._invalidate_cache()

    @staticmethod
    async def get_prices_by_slugs(
        db: AsyncSession, slugs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return user-facing prices keyed by routing_slug. Read-only helper
        kept for parity with the source — no cache invalidation needed."""
        if not slugs:
            return {}
        from sqlalchemy import select
        rows = await db.execute(
            select(
                ModelCatalog.routing_slug,
                ModelCatalog.sale_input_per_million,
                ModelCatalog.sale_output_per_million,
                ModelCatalog.sale_cached_input_per_million,
            ).where(
                ModelCatalog.routing_slug.in_(slugs),
                ModelCatalog.routing_slug.isnot(None),
            )
        )
        result: dict[str, dict[str, Any]] = {}
        for routing_slug, inp, out, cached in rows.all():
            result[routing_slug] = {
                "input": inp or 0,
                "output": out or 0,
                "cached_input": cached or 0,
            }
        missing = set(slugs) - set(result.keys())
        if missing:
            logger.warning("No user-facing prices found for model slugs: %s", missing)
        return result


__all__ = ["ModelCatalogService"]
