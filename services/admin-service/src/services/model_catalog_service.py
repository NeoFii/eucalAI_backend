"""Business operations for the admin-owned model catalog."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from repositories import (
    ModelCategoryRepository,
    ModelVendorRepository,
    SupportedModelRepository,
)
from services.audit_service import AdminAuditService
from schemas.model_catalog import (
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
from common.core.exceptions import NotFoundException, ValidationException

logger = logging.getLogger(__name__)


class ModelCatalogService:
    """Read and mutate the model catalog."""

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
    def _model_item(model: SupportedModel, *, detail: bool = False) -> SupportedModelItem:
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
            "price_input_per_m_fen": model.price_input_per_m_fen,
            "price_output_per_m_fen": model.price_output_per_m_fen,
            "price_cached_input_per_m_fen": model.price_cached_input_per_m_fen,
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

    @staticmethod
    async def list_vendors(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
        active_only: bool = True,
    ) -> tuple[list[ModelVendorItem], int]:
        vendors, total = await ModelVendorRepository(db).list_vendors(
            page=page,
            page_size=page_size,
            active_only=active_only,
        )
        return [ModelCatalogService._vendor_item(vendor) for vendor in vendors], total

    @staticmethod
    async def list_categories(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 100,
        active_only: bool = True,
    ) -> tuple[list[ModelCategoryItem], int]:
        categories, total = await ModelCategoryRepository(db).list_categories(
            page=page,
            page_size=page_size,
            active_only=active_only,
        )
        return [ModelCatalogService._category_item(category) for category in categories], total

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
        """List supported models.

        参数语义：
        - active_only: 兼容旧调用，True 时仅返回 is_active=True 的模型（用户端走这一支）
        - status: 管理端三态过滤，覆盖 active_only：
            * "active"   仅在线模型
            * "archived" 仅归档模型 (is_active=False)
            * "all"      不过滤
        """
        models, total = await SupportedModelRepository(db).list_models(
            page=page,
            page_size=page_size,
            active_only=active_only,
            status=status,
            category=category,
            vendors=vendors,
            q=q,
        )
        return [ModelCatalogService._model_item(model) for model in models], total

    @staticmethod
    async def get_model_by_slug(
        db: AsyncSession,
        slug: str,
        *,
        active_only: bool = True,
    ) -> SupportedModelDetail:
        model = await SupportedModelRepository(db).get_by_slug(slug, active_only=active_only)
        if model is None:
            raise NotFoundException("model not found")
        return ModelCatalogService._model_item(model, detail=True)

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
            raise ValidationException("vendor slug already exists")
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
        await db.refresh(vendor)
        return ModelCatalogService._vendor_item(vendor)

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
            raise ValidationException("category key already exists")
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
        await db.refresh(category)
        return ModelCatalogService._category_item(category)

    @staticmethod
    async def _resolve_vendor(db: AsyncSession, slug: str) -> ModelVendor:
        vendor = await ModelVendorRepository(db).get_by_slug(slug)
        if vendor is None:
            raise NotFoundException("vendor not found")
        return vendor

    @staticmethod
    async def _resolve_categories(
        db: AsyncSession,
        keys: list[str],
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
        model: SupportedModel,
        categories: list[ModelCategory],
    ) -> None:
        existing_by_category_id: dict[int, SupportedModelCategoryMap] = {}
        for link in model.category_links:
            category_id = link.category_id or (link.category.id if link.category else None)
            if category_id is not None:
                existing_by_category_id[category_id] = link

        next_links: list[SupportedModelCategoryMap] = []
        for index, category in enumerate(categories):
            category_id = category.id
            link = existing_by_category_id.get(category_id) if category_id is not None else None
            if link is None:
                link = SupportedModelCategoryMap(category=category, category_id=category_id)
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
        model_repo = SupportedModelRepository(db)
        if await model_repo.get_by_slug(payload.slug, active_only=False):
            raise ValidationException("model slug already exists")

        vendor = await ModelCatalogService._resolve_vendor(db, payload.vendor_slug)
        categories = await ModelCatalogService._resolve_categories(db, payload.category_keys)
        model = SupportedModel(
            slug=payload.slug,
            routing_slug=payload.routing_slug,
            name=payload.name,
            vendor=vendor,
            summary=payload.summary,
            description=payload.description,
            price_input_per_m_fen=payload.price_input_per_m_fen,
            price_output_per_m_fen=payload.price_output_per_m_fen,
            price_cached_input_per_m_fen=payload.price_cached_input_per_m_fen,
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
        model_repo = SupportedModelRepository(db)
        model = await model_repo.get_by_slug(slug, active_only=False)
        if model is None:
            raise NotFoundException("model not found")

        data = payload.model_dump(exclude_unset=True)
        if "vendor_slug" in data:
            model.vendor = await ModelCatalogService._resolve_vendor(db, data.pop("vendor_slug"))
        if "category_keys" in data:
            categories = await ModelCatalogService._resolve_categories(
                db,
                data.pop("category_keys"),
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
        """归档模型：将 is_active 置为 False，保留记录便于后续恢复或审计。"""
        model = await SupportedModelRepository(db).get_by_slug(slug, active_only=False)
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

    @staticmethod
    async def get_prices_by_slugs(
        db: AsyncSession, slugs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return user-facing prices keyed by routing_slug (pool_models.model_slug)."""
        if not slugs:
            return {}
        from sqlalchemy import select
        rows = await db.execute(
            select(
                SupportedModel.routing_slug,
                SupportedModel.price_input_per_m_fen,
                SupportedModel.price_output_per_m_fen,
                SupportedModel.price_cached_input_per_m_fen,
            ).where(
                SupportedModel.routing_slug.in_(slugs),
                SupportedModel.routing_slug.isnot(None),
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
