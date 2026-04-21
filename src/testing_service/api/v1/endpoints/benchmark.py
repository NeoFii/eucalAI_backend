# -*- coding: utf-8 -*-
"""Benchmark endpoints backed by ARQ jobs."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from testing_service.dependencies import AdminPrincipal, get_current_admin, get_db_session
from testing_service.benchmark.jobs import (
    BenchmarkQueueUnavailableError,
    enqueue_full_benchmark_job,
    enqueue_single_benchmark_job,
)
from testing_service.config import get_settings
from testing_service.benchmark import (
    AdminProbeAuditListResponse,
    AdminProbeAuditResponse,
    BenchmarkJobAcceptedResponse,
    BenchmarkJobStatusResponse,
    BenchmarkStatsSummaryResponse,
    BenchmarkTrendResponse,
    ProviderTrendLine,
    TrendDataPoint,
)
from testing_service.schemas import ApiResponse
from testing_service.benchmark import AdminProbeAuditService, BenchmarkJobService
from testing_service.catalog import ModelService
from testing_service.provider_config import OfferingService, PerformanceMetricService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _resolve_probe_region(region: str | None = None) -> str | None:
    return region or get_settings().probe_region or None


async def _commit_job(db: AsyncSession) -> None:
    """Persist benchmark job state before handing control to ARQ or the client."""
    await db.commit()


def _serialize_job(job) -> BenchmarkJobStatusResponse:
    queued_count = max(job.total_offerings - job.completed_offerings, 0)
    return BenchmarkJobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        trigger_source=job.trigger_source,
        requested_by_admin_id=job.requested_by_admin_id,
        scope_offering_id=job.scope_offering_id,
        total_offerings=job.total_offerings,
        completed_offerings=job.completed_offerings,
        succeeded_offerings=job.succeeded_offerings,
        failed_offerings=job.failed_offerings,
        queued_count=queued_count,
        error_message=job.error_message,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/stats/summary",
    response_model=ApiResponse[BenchmarkStatsSummaryResponse],
    summary="Get benchmark summary stats",
)
async def get_benchmark_stats_summary(
    n: int = Query(5, description="Use the latest N successful probes"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    offerings = await OfferingService.list_all_active(db)
    resolved_region = _resolve_probe_region()
    model_map: dict[int, dict] = {}
    for offering in offerings:
        model_id = offering.model_id
        if model_id not in model_map:
            model = await ModelService.get_by_id(db, model_id)
            if not model:
                continue
            model_map[model_id] = {
                "model_slug": model.slug,
                "model_name": model.name,
                "vendor_name": model.vendor.name if model.vendor else "",
                "offerings": [],
            }

        metrics_list = await OfferingService.get_metrics(db, offering.id, n=n, region=resolved_region)
        metrics_data = None
        if metrics_list:
            metrics = metrics_list[0]
            metrics_data = {
                "avg_throughput_tps": metrics.avg_throughput_tps,
                "avg_ttft_ms": metrics.avg_ttft_ms,
                "avg_e2e_latency_ms": metrics.avg_e2e_latency_ms,
                "sample_count": metrics.sample_count,
                "last_measured_at": metrics.last_measured_at.isoformat() if metrics.last_measured_at else None,
            }

        latest_probe = await PerformanceMetricService.get_latest_by_offering(db, offering.id)
        latest_probe_data = None
        if latest_probe:
            latest_probe_data = {
                "success": latest_probe.success,
                "error_code": latest_probe.error_code,
                "measured_at": latest_probe.measured_at.isoformat() if latest_probe.measured_at else None,
                "probe_region": latest_probe.probe_region,
            }

        provider = offering.provider
        model_map[model_id]["offerings"].append(
            {
                "offering_id": offering.id,
                "provider_name": provider.name if provider else "Unknown",
                "provider_slug": provider.slug if provider else "",
                "metrics": metrics_data,
                "latest_probe": latest_probe_data,
            }
        )

    items = list(model_map.values())
    return {
        "code": 200,
        "message": "success",
        "data": {"items": items, "total": len(items)},
    }


@router.post(
    "/probe/trigger",
    response_model=ApiResponse[BenchmarkJobAcceptedResponse],
    summary="Queue a full benchmark run",
)
async def trigger_probe_all(
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    if not settings.probe_enabled:
        raise HTTPException(status_code=503, detail="benchmark probe is disabled")

    offerings = await OfferingService.list_all_active(db)
    job = await BenchmarkJobService.create(
        db,
        job_type="full",
        requested_by_admin_id=current_admin.id,
        total_offerings=len(offerings),
        trigger_source="manual",
    )
    await _commit_job(db)
    if not offerings:
        await BenchmarkJobService.mark_succeeded_empty(db, job.job_id)
        await _commit_job(db)
        return {
            "code": 200,
            "message": "success",
            "data": {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "status": "succeeded",
                "accepted": True,
                "queued_count": 0,
            },
        }

    try:
        await enqueue_full_benchmark_job(job.job_id)
    except BenchmarkQueueUnavailableError as exc:
        await BenchmarkJobService.mark_failed(db, job.job_id, str(exc))
        await _commit_job(db)
        raise HTTPException(status_code=503, detail=f"benchmark queue unavailable: {exc}") from exc

    logger.info("Admin triggered full benchmark job=%s offerings=%d", job.job_id, len(offerings))
    return {
        "code": 200,
        "message": "success",
        "data": {
            "job_id": job.job_id,
            "job_type": job.job_type,
            "status": job.status,
            "accepted": True,
            "queued_count": len(offerings),
        },
    }


@router.post(
    "/probe/{offering_id}",
    response_model=ApiResponse[BenchmarkJobAcceptedResponse],
    summary="Queue a single benchmark run",
)
async def trigger_probe_one(
    offering_id: int,
    current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    if not settings.probe_enabled:
        raise HTTPException(status_code=503, detail="benchmark probe is disabled")

    offering = await OfferingService.get_by_id(db, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="offering not found")
    if not offering.is_active:
        raise HTTPException(status_code=400, detail="offering is inactive")

    job = await BenchmarkJobService.create(
        db,
        job_type="single",
        requested_by_admin_id=current_admin.id,
        scope_offering_id=offering_id,
        total_offerings=1,
        trigger_source="manual",
    )
    await _commit_job(db)
    try:
        await enqueue_single_benchmark_job(job.job_id, offering_id, current_admin.id)
    except BenchmarkQueueUnavailableError as exc:
        await BenchmarkJobService.mark_failed(db, job.job_id, str(exc))
        await _commit_job(db)
        raise HTTPException(status_code=503, detail=f"benchmark queue unavailable: {exc}") from exc

    logger.info("Admin triggered single benchmark job=%s offering=%d", job.job_id, offering_id)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "job_id": job.job_id,
            "job_type": job.job_type,
            "status": job.status,
            "accepted": True,
            "queued_count": 1,
        },
    }


@router.get(
    "/jobs/{job_id}",
    response_model=ApiResponse[BenchmarkJobStatusResponse],
    summary="Get benchmark job status",
)
async def get_benchmark_job(
    job_id: str,
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await BenchmarkJobService.get_by_job_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="benchmark job not found")
    return {"code": 200, "message": "success", "data": _serialize_job(job).model_dump()}


@router.get(
    "/probe-audits",
    response_model=ApiResponse[AdminProbeAuditListResponse],
    summary="List manual benchmark probe audit records",
)
async def get_probe_audits(
    offering_id: int | None = Query(default=None),
    job_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _current_admin: AdminPrincipal = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await AdminProbeAuditService.list(db, offering_id=offering_id, job_id=job_id, limit=limit)
    data = AdminProbeAuditListResponse(
        items=[AdminProbeAuditResponse.model_validate(item) for item in items],
        total=len(items),
    )
    return {"code": 200, "message": "success", "data": data.model_dump()}


@router.get(
    "/trends",
    response_model=ApiResponse[BenchmarkTrendResponse],
    summary="Get benchmark trends for one model",
)
async def get_benchmark_trends(
    model_slug: str = Query(..., description="Model slug"),
    days: int = Query(7, ge=1, le=30, description="Date range"),
    region: str | None = Query(None, description="Probe region filter"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    model = await ModelService.get_by_slug(db, model_slug)
    if not model:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "model_slug": model_slug,
                "model_name": "",
                "days": days,
                "date_range": "",
                "providers": [],
            },
        }

    raw_rows = await PerformanceMetricService.get_trend_data(
        db,
        model.id,
        days=days,
        region=_resolve_probe_region(region),
    )
    provider_data: dict[int, dict] = {}
    for row in raw_rows:
        provider_entry = provider_data.setdefault(
            row["provider_id"],
            {
                "provider_id": row["provider_id"],
                "provider_name": row["provider_name"],
                "provider_slug": row["provider_slug"],
                "provider_logo_url": row["provider_logo_url"],
                "points": [],
            },
        )
        provider_entry["points"].append(row)

    providers: list[ProviderTrendLine] = []
    for provider_info in provider_data.values():
        data_points: list[TrendDataPoint] = []
        throughputs: list[float] = []
        ttfts: list[int] = []
        for row in provider_info["points"]:
            data_points.append(
                TrendDataPoint(
                    date=row["date"].isoformat(),
                    avg_throughput_tps=row["avg_throughput_tps"],
                    avg_ttft_ms=row["avg_ttft_ms"],
                    avg_e2e_latency_ms=row["avg_e2e_latency_ms"],
                    sample_count=row["sample_count"],
                )
            )
            if row["avg_throughput_tps"] is not None:
                throughputs.append(row["avg_throughput_tps"])
            if row["avg_ttft_ms"] is not None:
                ttfts.append(row["avg_ttft_ms"])

        providers.append(
            ProviderTrendLine(
                provider_id=provider_info["provider_id"],
                provider_name=provider_info["provider_name"],
                provider_slug=provider_info["provider_slug"],
                provider_logo_url=provider_info["provider_logo_url"],
                data_points=data_points,
                min_throughput=round(min(throughputs), 2) if throughputs else None,
                max_throughput=round(max(throughputs), 2) if throughputs else None,
                avg_throughput=round(sum(throughputs) / len(throughputs), 2) if throughputs else None,
                min_ttft=min(ttfts) if ttfts else None,
                max_ttft=max(ttfts) if ttfts else None,
                avg_ttft=round(sum(ttfts) / len(ttfts)) if ttfts else None,
            )
        )

    providers.sort(key=lambda item: item.avg_throughput or 0, reverse=True)
    if raw_rows:
        start_date = raw_rows[0]["date"]
        end_date = raw_rows[-1]["date"]
    else:
        end_date = now()
        start_date = end_date - timedelta(days=days - 1)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "model_slug": model.slug,
            "model_name": model.name,
            "days": days,
            "date_range": f"{start_date.strftime('%m.%d %H:%M')} - {end_date.strftime('%m.%d %H:%M')}",
            "providers": [provider.model_dump() for provider in providers],
        },
    }
