# -*- coding: utf-8 -*-
"""Benchmark job dispatching and worker execution."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from testing_service.db import close_db, create_engine, get_db_context, init_session_factory
from common.utils.timezone import now
from testing_service.config import get_settings
from testing_service.benchmarking import AdminProbeAuditService, BenchmarkJobService
from testing_service.provider_config import OfferingService
from testing_service.benchmark.queue import BenchmarkQueueUnavailableError, build_redis_settings, enqueue_job

logger = logging.getLogger(__name__)

FULL_BENCHMARK_DISPATCH_FN = "dispatch_full_benchmark_job"
FULL_BENCHMARK_CHILD_FN = "run_full_benchmark_probe"
SINGLE_BENCHMARK_CHILD_FN = "run_single_benchmark_probe"


@dataclass
class ProbeExecutionResult:
    offering_id: int
    model_id: Optional[int]
    provider_id: Optional[int]
    success: bool
    error_code: Optional[str]
    throughput_tps: Optional[float]
    ttft_ms: Optional[int]
    e2e_latency_ms: Optional[int]
    prompt_tokens: Optional[int]
    output_tokens: Optional[int]
    probe_region: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


async def enqueue_full_benchmark_job(job_id: str):
    return await enqueue_job(FULL_BENCHMARK_DISPATCH_FN, job_id, _job_id=f"dispatch:{job_id}")


async def enqueue_single_benchmark_job(job_id: str, offering_id: int, requested_by_admin_id: Optional[int]):
    return await enqueue_job(
        SINGLE_BENCHMARK_CHILD_FN,
        job_id,
        offering_id,
        requested_by_admin_id,
        _job_id=f"single:{job_id}:{offering_id}",
    )


async def enqueue_scheduled_benchmark() -> str | None:
    settings = get_settings()
    if not settings.probe_enabled or not settings.benchmark_enable_scheduler_enqueue:
        return None

    async with get_db_context() as db:
        offerings = await OfferingService.list_all_active(db)
        job = await BenchmarkJobService.create(
            db,
            job_type="full",
            requested_by_admin_id=None,
            total_offerings=len(offerings),
            trigger_source="scheduler",
        )
    if job.total_offerings == 0:
        async with get_db_context() as db:
            await BenchmarkJobService.mark_succeeded_empty(db, job.job_id)
        return job.job_id

    try:
        await enqueue_full_benchmark_job(job.job_id)
    except BenchmarkQueueUnavailableError as exc:
        async with get_db_context() as db:
            await BenchmarkJobService.mark_failed(db, job.job_id, str(exc))
        logger.error("Failed to enqueue scheduled benchmark job %s: %s", job.job_id, exc)
        return None
    logger.info("Scheduled benchmark job queued: %s", job.job_id)
    return job.job_id


async def on_worker_startup(ctx: dict) -> None:
    settings = get_settings()
    create_engine(settings.DATABASE_URL)
    init_session_factory()
    ctx["settings"] = settings
    logger.info("Benchmark worker started with concurrency=%s", settings.benchmark_worker_concurrency)


async def on_worker_shutdown(ctx: dict) -> None:
    del ctx
    await close_db()
    logger.info("Benchmark worker stopped")


async def dispatch_full_benchmark_job(ctx: dict, benchmark_job_id: str) -> None:
    async with get_db_context() as db:
        job = await BenchmarkJobService.get_by_job_id(db, benchmark_job_id)
        if job is None:
            logger.warning("Dispatch skipped, benchmark job missing: %s", benchmark_job_id)
            return
        offerings = await OfferingService.list_all_active(db)
        offering_ids = [offering.id for offering in offerings]
        await BenchmarkJobService.update_total_offerings(db, benchmark_job_id, len(offering_ids))
        if not offering_ids:
            await BenchmarkJobService.mark_succeeded_empty(db, benchmark_job_id)
            logger.info("Benchmark job %s completed without active offerings", benchmark_job_id)
            return

    redis = ctx["redis"]
    enqueued = 0
    for offering_id in offering_ids:
        job = await redis.enqueue_job(
            FULL_BENCHMARK_CHILD_FN,
            benchmark_job_id,
            offering_id,
            _job_id=f"full:{benchmark_job_id}:{offering_id}",
        )
        if job is not None:
            enqueued += 1

    if enqueued == 0:
        async with get_db_context() as db:
            await BenchmarkJobService.mark_failed(db, benchmark_job_id, "No child benchmark jobs were enqueued")
        logger.error("Dispatch failed, no benchmark children enqueued: %s", benchmark_job_id)
        return

    logger.info("Benchmark job %s dispatched %d offering probes", benchmark_job_id, enqueued)


async def _execute_probe(offering_id: int) -> ProbeExecutionResult:
    from testing_service.benchmark.probe_runner import ProbeRunner

    async with get_db_context() as db:
        runner = ProbeRunner(db, probe_region=get_settings().probe_region)
        return await runner.execute(offering_id)


async def run_full_benchmark_probe(ctx: dict, benchmark_job_id: str, offering_id: int) -> None:
    try:
        result = await _execute_probe(offering_id)
        async with get_db_context() as db:
            from testing_service.benchmark.probe_runner import ProbeRunner

            runner = ProbeRunner(db, probe_region=result.probe_region or get_settings().probe_region)
            await BenchmarkJobService.mark_running(db, benchmark_job_id)
            await runner.persist_performance_metric(result)
            await BenchmarkJobService.record_child_result(
                db,
                job_id=benchmark_job_id,
                success=result.success,
                error_message=result.error_code,
            )
        logger.info(
            "Full benchmark probe finished job=%s offering=%s success=%s",
            benchmark_job_id,
            offering_id,
            result.success,
        )
    except Exception as exc:
        logger.exception("Full benchmark probe failed job=%s offering=%s", benchmark_job_id, offering_id)
        async with get_db_context() as db:
            await BenchmarkJobService.mark_running(db, benchmark_job_id)
            await BenchmarkJobService.record_child_result(
                db,
                job_id=benchmark_job_id,
                success=False,
                error_message=str(exc)[:255],
            )
        raise


async def run_single_benchmark_probe(
    ctx: dict,
    benchmark_job_id: str,
    offering_id: int,
    requested_by_admin_id: Optional[int],
) -> None:
    try:
        result = await _execute_probe(offering_id)
        async with get_db_context() as db:
            await BenchmarkJobService.mark_running(db, benchmark_job_id)
            await AdminProbeAuditService.create(
                db,
                job_id=benchmark_job_id,
                offering_id=result.offering_id,
                model_id=result.model_id,
                provider_id=result.provider_id,
                triggered_by_admin_id=requested_by_admin_id,
                success=result.success,
                status="completed" if result.success else "failed",
                error_code=result.error_code,
                ttft_ms=result.ttft_ms,
                e2e_latency_ms=result.e2e_latency_ms,
                throughput_tps=result.throughput_tps,
                prompt_tokens=result.prompt_tokens,
                output_tokens=result.output_tokens,
                probe_region=result.probe_region,
                started_at=result.started_at,
                finished_at=result.finished_at or now(),
            )
            await BenchmarkJobService.record_child_result(
                db,
                job_id=benchmark_job_id,
                success=result.success,
                error_message=result.error_code,
            )
        logger.info(
            "Single benchmark probe finished job=%s offering=%s success=%s details=%s",
            benchmark_job_id,
            offering_id,
            result.success,
            asdict(result),
        )
    except Exception as exc:
        logger.exception("Single benchmark probe failed job=%s offering=%s", benchmark_job_id, offering_id)
        async with get_db_context() as db:
            await BenchmarkJobService.mark_running(db, benchmark_job_id)
            await BenchmarkJobService.record_child_result(
                db,
                job_id=benchmark_job_id,
                success=False,
                error_message=str(exc)[:255],
            )
        raise


def get_worker_settings_kwargs() -> dict:
    settings = get_settings()
    return {
        "functions": [
            dispatch_full_benchmark_job,
            run_full_benchmark_probe,
            run_single_benchmark_probe,
        ],
        "redis_settings": build_redis_settings(settings.benchmark_queue_redis_url),
        "max_jobs": settings.benchmark_worker_concurrency,
        "job_timeout": settings.benchmark_job_timeout_seconds,
        "on_startup": on_worker_startup,
        "on_shutdown": on_worker_shutdown,
    }
