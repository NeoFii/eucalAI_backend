"""Model catalog data access."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from testing_service.models import (
    Model,
    ModelCategory,
    ModelCategoryMap,
    ModelProviderOffering,
    ModelVendor,
    Provider,
    ProviderMetricsRanked,
    ProviderPerformanceMetric,
)
from testing_service.schemas import ModelCategoryBrief, OfferingMetricsResponse


def _serialize_router_candidate(offering: ModelProviderOffering, provider: Provider) -> dict:
    api_base_url = provider.probe_api_base_url or offering.api_base_url
    return {
        "offering_id": int(offering.id),
        "model_id": int(offering.model_id),
        "provider_id": int(provider.id),
        "provider_slug": provider.slug,
        "provider_name": provider.name,
        "provider_model_name": (offering.provider_model_name or "").strip(),
        "api_base_url": api_base_url.rstrip("/") if api_base_url else "",
        "encrypted_api_key": {
            "ciphertext": provider.probe_api_key_ciphertext,
            "iv": provider.probe_api_key_iv,
            "tag": provider.probe_api_key_tag,
        },
        "input_price_per_m": (
            float(offering.price_input_per_m) if offering.price_input_per_m is not None else None
        ),
        "output_price_per_m": (
            float(offering.price_output_per_m) if offering.price_output_per_m is not None else None
        ),
    }


class VendorRepository:
    """Read-side data access for model vendors."""

    @staticmethod
    async def list_all(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ModelVendor], int]:
        query = select(ModelVendor).where(ModelVendor.deleted_at.is_(None)).order_by(ModelVendor.name)
        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
        items = list(
            (await db.execute(query.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )
        return items, total

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[ModelVendor]:
        result = await db.execute(
            select(ModelVendor).where(and_(ModelVendor.slug == slug, ModelVendor.deleted_at.is_(None)))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, vendor_id: int) -> Optional[ModelVendor]:
        result = await db.execute(
            select(ModelVendor).where(
                and_(ModelVendor.id == vendor_id, ModelVendor.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()


class CategoryRepository:
    """Read-side data access for model categories."""

    @staticmethod
    async def list_all(db: AsyncSession) -> List[ModelCategory]:
        result = await db.execute(
            select(ModelCategory)
            .where(ModelCategory.is_active == True)
            .order_by(ModelCategory.sort_order, ModelCategory.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_key(db: AsyncSession, key: str) -> Optional[ModelCategory]:
        result = await db.execute(select(ModelCategory).where(ModelCategory.key == key))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, category_id: int) -> Optional[ModelCategory]:
        result = await db.execute(select(ModelCategory).where(ModelCategory.id == category_id))
        return result.scalar_one_or_none()


class ProviderRepository:
    """Read-side data access for providers."""

    @staticmethod
    async def list_all(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Provider], int]:
        query = (
            select(Provider)
            .where(Provider.deleted_at.is_(None))
            .order_by(Provider.is_active.desc(), Provider.name)
        )
        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
        items = list(
            (await db.execute(query.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )
        return items, total

    @staticmethod
    async def get_by_id(db: AsyncSession, provider_id: int) -> Optional[Provider]:
        result = await db.execute(
            select(Provider).where(
                and_(Provider.id == provider_id, Provider.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Provider]:
        result = await db.execute(
            select(Provider).where(and_(Provider.slug == slug, Provider.deleted_at.is_(None)))
        )
        return result.scalar_one_or_none()


class ModelRepository:
    """Read-side data access for models and category projections."""

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        category_key: Optional[str] = None,
        vendor_slugs: Optional[List[str]] = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Model], int]:
        query = (
            select(Model)
            .join(ModelVendor, Model.vendor_id == ModelVendor.id)
            .where(Model.is_active == True)
        )

        if category_key:
            query = (
                query.join(ModelCategoryMap, ModelCategoryMap.model_id == Model.id)
                .join(ModelCategory, ModelCategoryMap.category_id == ModelCategory.id)
                .where(ModelCategory.key == category_key)
                .order_by(ModelCategoryMap.sort_order, Model.sort_order, Model.name)
            )
        else:
            query = query.order_by(Model.sort_order, Model.name)

        if vendor_slugs:
            query = query.where(ModelVendor.slug.in_(vendor_slugs))

        if q:
            like_pattern = f"%{q}%"
            query = query.where(
                or_(
                    Model.name.ilike(like_pattern),
                    Model.slug.ilike(like_pattern),
                    Model.description.ilike(like_pattern),
                )
            )

        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
        items = list(
            (await db.execute(query.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )
        return items, total

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Model]:
        result = await db.execute(select(Model).where(Model.slug == slug))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, model_id: int) -> Optional[Model]:
        result = await db.execute(select(Model).where(Model.id == model_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_category_briefs(db: AsyncSession, model_id: int) -> List[ModelCategoryBrief]:
        rows = await db.execute(
            select(
                ModelCategory.key,
                ModelCategory.name,
                ModelCategoryMap.sort_order,
            )
            .join(ModelCategoryMap, ModelCategoryMap.category_id == ModelCategory.id)
            .where(ModelCategoryMap.model_id == model_id)
            .where(ModelCategory.is_active == True)
            .order_by(ModelCategoryMap.sort_order)
        )
        return [
            ModelCategoryBrief(key=row.key, name=row.name, sort_order=row.sort_order)
            for row in rows.all()
        ]

    @staticmethod
    async def list_router_models(db: AsyncSession) -> dict:
        rows = (
            await db.execute(
                select(
                    Model.slug,
                    ModelProviderOffering.provider_model_name,
                    ModelProviderOffering,
                    Provider,
                )
                .join(ModelProviderOffering, ModelProviderOffering.model_id == Model.id)
                .join(Provider, ModelProviderOffering.provider_id == Provider.id)
                .where(Model.is_active.is_(True))
                .where(Provider.is_active.is_(True))
                .where(ModelProviderOffering.is_active.is_(True))
                .where(ModelProviderOffering.deleted_at.is_(None))
                .where(Provider.deleted_at.is_(None))
                .where(ModelProviderOffering.provider_model_name.is_not(None))
            )
        ).all()

        seen: set[str] = set()
        aggregates: dict[str, list[float | int | bool]] = defaultdict(lambda: [0.0, 0, False])
        for model_slug, provider_model_name, offering, provider in rows:
            api_base_url = provider.probe_api_base_url or offering.api_base_url
            has_key = bool(
                provider.probe_api_key_ciphertext
                and provider.probe_api_key_iv
                and provider.probe_api_key_tag
            )
            if not api_base_url or not has_key:
                continue

            if model_slug:
                seen.add(model_slug)
                total, count, has_unknown = aggregates[model_slug]
                if offering.price_input_per_m is None or offering.price_output_per_m is None:
                    aggregates[model_slug] = [total, count, True]
                else:
                    total += float(offering.price_input_per_m + offering.price_output_per_m)
                    count += 1
                    aggregates[model_slug] = [total, count, has_unknown]

            if provider_model_name:
                seen.add(f"{provider.slug}:{provider_model_name}")

        priced = []
        fallback = []
        for slug, (total, count, has_unknown) in aggregates.items():
            if count > 0:
                priced.append((slug, total / count))
            elif has_unknown:
                fallback.append(slug)
        priced.sort(key=lambda item: (item[1], item[0]))
        fallback.sort()

        return {
            "items": [
                {"id": item, "object": "model", "owned_by": "eucal-router"}
                for item in sorted(seen)
            ],
            "ranked_logical_models": [slug for slug, _ in priced] + fallback,
        }


class OfferingRepository:
    """Read-side data access for offerings and benchmark metric projections."""

    @staticmethod
    async def get_by_id(db: AsyncSession, offering_id: int) -> Optional[ModelProviderOffering]:
        result = await db.execute(
            select(ModelProviderOffering).where(
                and_(
                    ModelProviderOffering.id == offering_id,
                    ModelProviderOffering.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        result = await db.execute(
            select(ModelProviderOffering).where(
                and_(
                    ModelProviderOffering.model_id == model_id,
                    ModelProviderOffering.is_active == True,
                    ModelProviderOffering.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all_active(db: AsyncSession) -> List[ModelProviderOffering]:
        result = await db.execute(
            select(ModelProviderOffering).where(
                and_(
                    ModelProviderOffering.is_active == True,
                    ModelProviderOffering.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all_by_model(db: AsyncSession, model_id: int) -> List[ModelProviderOffering]:
        result = await db.execute(
            select(ModelProviderOffering)
            .where(
                and_(
                    ModelProviderOffering.model_id == model_id,
                    ModelProviderOffering.deleted_at.is_(None),
                )
            )
            .order_by(ModelProviderOffering.is_active.desc(), ModelProviderOffering.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_provider_counts(
        db: AsyncSession,
        model_ids: list[int],
    ) -> dict[int, int]:
        if not model_ids:
            return {}

        rows = await db.execute(
            select(
                ModelProviderOffering.model_id,
                func.count(ModelProviderOffering.id).label("provider_count"),
            )
            .join(Provider, Provider.id == ModelProviderOffering.provider_id)
            .where(ModelProviderOffering.model_id.in_(model_ids))
            .where(ModelProviderOffering.is_active == True)
            .where(ModelProviderOffering.deleted_at.is_(None))
            .where(Provider.is_active == True)
            .where(Provider.deleted_at.is_(None))
            .group_by(ModelProviderOffering.model_id)
        )
        return {int(row.model_id): int(row.provider_count) for row in rows.all()}

    @staticmethod
    async def get_metrics(
        db: AsyncSession,
        offering_id: int,
        n: int = 5,
        region: Optional[str] = None,
    ) -> List[OfferingMetricsResponse]:
        stmt = (
            select(
                ProviderMetricsRanked.probe_region,
                func.round(func.avg(ProviderMetricsRanked.throughput_tps), 2).label("avg_throughput_tps"),
                func.round(func.avg(ProviderMetricsRanked.ttft_ms), 0).label("avg_ttft_ms"),
                func.round(func.avg(ProviderMetricsRanked.e2e_latency_ms), 0).label("avg_e2e_latency_ms"),
                func.count().label("sample_count"),
                func.max(ProviderMetricsRanked.measured_at).label("last_measured_at"),
            )
            .where(ProviderMetricsRanked.offering_id == offering_id)
            .where(ProviderMetricsRanked.rn <= n)
            .group_by(ProviderMetricsRanked.probe_region)
        )
        if region:
            stmt = stmt.where(ProviderMetricsRanked.probe_region == region)

        rows = (await db.execute(stmt)).all()
        return [
            OfferingMetricsResponse(
                probe_region=row.probe_region,
                avg_throughput_tps=float(row.avg_throughput_tps) if row.avg_throughput_tps else None,
                avg_ttft_ms=int(row.avg_ttft_ms) if row.avg_ttft_ms else None,
                avg_e2e_latency_ms=int(row.avg_e2e_latency_ms) if row.avg_e2e_latency_ms else None,
                sample_count=row.sample_count,
                last_measured_at=row.last_measured_at,
            )
            for row in rows
        ]

    @staticmethod
    async def get_latest_metric_by_offering(
        db: AsyncSession,
        offering_id: int,
    ) -> Optional[ProviderPerformanceMetric]:
        result = await db.execute(
            select(ProviderPerformanceMetric)
            .where(ProviderPerformanceMetric.offering_id == offering_id)
            .order_by(
                ProviderPerformanceMetric.measured_at.desc(),
                ProviderPerformanceMetric.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_trend_data(
        db: AsyncSession,
        model_id: int,
        days: int = 7,
        region: Optional[str] = None,
    ) -> list[dict]:
        current = now()
        cutoff = datetime(current.year, current.month, current.day) - timedelta(days=days - 1)

        stmt = (
            select(
                ProviderPerformanceMetric.measured_at.label("date"),
                Provider.id.label("provider_id"),
                Provider.name.label("provider_name"),
                Provider.slug.label("provider_slug"),
                Provider.logo_url.label("provider_logo_url"),
                func.round(func.avg(ProviderPerformanceMetric.throughput_tps), 2).label(
                    "avg_throughput_tps"
                ),
                func.round(func.avg(ProviderPerformanceMetric.ttft_ms), 0).label("avg_ttft_ms"),
                func.round(func.avg(ProviderPerformanceMetric.e2e_latency_ms), 0).label(
                    "avg_e2e_latency_ms"
                ),
                func.count().label("sample_count"),
            )
            .select_from(ProviderPerformanceMetric)
            .join(
                ModelProviderOffering,
                ModelProviderOffering.id == ProviderPerformanceMetric.offering_id,
            )
            .join(Provider, Provider.id == ModelProviderOffering.provider_id)
            .where(ModelProviderOffering.model_id == model_id)
            .where(ModelProviderOffering.deleted_at.is_(None))
            .where(ProviderPerformanceMetric.success == True)
            .where(ProviderPerformanceMetric.measured_at >= cutoff)
            .group_by(
                ProviderPerformanceMetric.measured_at,
                Provider.id,
                Provider.name,
                Provider.slug,
                Provider.logo_url,
            )
            .order_by(
                ProviderPerformanceMetric.measured_at.asc(),
                Provider.id.asc(),
            )
        )
        if region:
            stmt = stmt.where(ProviderPerformanceMetric.probe_region == region)

        rows = (await db.execute(stmt)).all()
        return [
            {
                "date": row.date,
                "provider_id": row.provider_id,
                "provider_name": row.provider_name,
                "provider_slug": row.provider_slug,
                "provider_logo_url": row.provider_logo_url,
                "avg_throughput_tps": (
                    float(row.avg_throughput_tps) if row.avg_throughput_tps is not None else None
                ),
                "avg_ttft_ms": int(row.avg_ttft_ms) if row.avg_ttft_ms is not None else None,
                "avg_e2e_latency_ms": (
                    int(row.avg_e2e_latency_ms) if row.avg_e2e_latency_ms is not None else None
                ),
                "sample_count": row.sample_count,
            }
            for row in rows
        ]

    @staticmethod
    async def resolve_router_routes(
        db: AsyncSession,
        *,
        model_name: str,
        provider_hint: Optional[str] = None,
    ) -> list[dict]:
        stmt = (
            select(ModelProviderOffering, Provider, Model)
            .join(Provider, ModelProviderOffering.provider_id == Provider.id)
            .join(Model, ModelProviderOffering.model_id == Model.id)
            .where(Model.is_active.is_(True))
            .where(Provider.is_active.is_(True))
            .where(ModelProviderOffering.is_active.is_(True))
            .where(ModelProviderOffering.deleted_at.is_(None))
            .where(Provider.deleted_at.is_(None))
            .where(ModelProviderOffering.provider_model_name.is_not(None))
            .where(
                or_(
                    Model.slug == model_name,
                    ModelProviderOffering.provider_model_name == model_name,
                )
            )
        )
        if provider_hint:
            stmt = stmt.where(Provider.slug == provider_hint)

        rows = (await db.execute(stmt)).all()
        candidates = []
        for offering, provider, _model in rows:
            api_base_url = provider.probe_api_base_url or offering.api_base_url
            if not api_base_url:
                continue
            if (
                not provider.probe_api_key_ciphertext
                or not provider.probe_api_key_iv
                or not provider.probe_api_key_tag
            ):
                continue
            provider_model_name = (offering.provider_model_name or "").strip()
            if not provider_model_name:
                continue
            candidates.append(_serialize_router_candidate(offering, provider))

        candidates.sort(
            key=lambda item: (
                float("inf")
                if item["input_price_per_m"] is None or item["output_price_per_m"] is None
                else item["input_price_per_m"] + item["output_price_per_m"],
                item["provider_slug"],
            )
        )
        return candidates

    @staticmethod
    async def get_router_offering(db: AsyncSession, offering_id: int) -> Optional[dict]:
        row = (
            await db.execute(
                select(ModelProviderOffering, Provider, Model)
                .join(Provider, ModelProviderOffering.provider_id == Provider.id)
                .join(Model, ModelProviderOffering.model_id == Model.id)
                .where(ModelProviderOffering.id == offering_id)
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        offering, provider, model = row
        payload = _serialize_router_candidate(offering, provider)
        payload["model_slug"] = model.slug
        payload["model_name"] = model.name
        return payload
