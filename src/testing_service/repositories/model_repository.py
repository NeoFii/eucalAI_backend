"""Model catalog data access."""

from __future__ import annotations

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


class OfferingRepository:
    """Read-side data access for offerings and benchmark metric projections."""

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
