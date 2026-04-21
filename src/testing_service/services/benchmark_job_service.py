# -*- coding: utf-8 -*-
"""Benchmark job and admin probe audit services."""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from testing_service.models import AdminProbeAuditLog, BenchmarkJob
from testing_service.repositories.benchmark_repository import (
    AdminProbeAuditRepository,
    BenchmarkJobRepository,
)

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "partial"}


class BenchmarkJobService:
    """Persist and update benchmark dispatch jobs."""

    @staticmethod
    def generate_job_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        job_type: str,
        requested_by_admin_id: Optional[int],
        scope_offering_id: Optional[int] = None,
        total_offerings: int = 0,
        trigger_source: str = "manual",
    ) -> BenchmarkJob:
        job = BenchmarkJob(
            job_id=BenchmarkJobService.generate_job_id(job_type),
            job_type=job_type,
            status="queued",
            requested_by_admin_id=requested_by_admin_id,
            scope_offering_id=scope_offering_id,
            trigger_source=trigger_source,
            total_offerings=total_offerings,
            queued_at=now(),
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    @staticmethod
    async def get_by_job_id(db: AsyncSession, job_id: str) -> Optional[BenchmarkJob]:
        return await BenchmarkJobRepository.get_by_job_id(db, job_id)

    @staticmethod
    async def update_total_offerings(db: AsyncSession, job_id: str, total_offerings: int) -> None:
        await BenchmarkJobRepository.update_total_offerings(db, job_id, total_offerings)

    @staticmethod
    async def mark_running(db: AsyncSession, job_id: str) -> None:
        await BenchmarkJobRepository.mark_running(db, job_id)

    @staticmethod
    async def mark_failed(db: AsyncSession, job_id: str, error_message: str) -> None:
        await BenchmarkJobRepository.mark_failed(db, job_id, error_message)

    @staticmethod
    async def mark_succeeded_empty(db: AsyncSession, job_id: str) -> None:
        await BenchmarkJobRepository.mark_succeeded_empty(db, job_id)

    @staticmethod
    async def record_child_result(
        db: AsyncSession,
        *,
        job_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> Optional[BenchmarkJob]:
        await BenchmarkJobRepository.increment_child_result(
            db,
            job_id=job_id,
            success=success,
            error_message=error_message,
        )
        job = await BenchmarkJobService.get_by_job_id(db, job_id)
        if job is None:
            return None
        if job.completed_offerings >= job.total_offerings:
            final_status = "succeeded"
            if job.failed_offerings > 0 and job.succeeded_offerings > 0:
                final_status = "partial"
            elif job.failed_offerings > 0 and job.succeeded_offerings == 0:
                final_status = "failed"
            await BenchmarkJobRepository.mark_terminal_if_incomplete(
                db,
                job_id=job_id,
                final_status=final_status,
                terminal_statuses=TERMINAL_JOB_STATUSES,
            )
            job = await BenchmarkJobService.get_by_job_id(db, job_id)
        return job


class AdminProbeAuditService:
    """Read and write manual probe audit rows."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        job_id: str,
        offering_id: Optional[int],
        model_id: Optional[int],
        provider_id: Optional[int],
        triggered_by_admin_id: Optional[int],
        success: bool,
        status: str,
        error_code: Optional[str],
        ttft_ms: Optional[int],
        e2e_latency_ms: Optional[int],
        throughput_tps: Optional[float],
        prompt_tokens: Optional[int],
        output_tokens: Optional[int],
        probe_region: Optional[str],
        started_at,
        finished_at,
    ) -> AdminProbeAuditLog:
        audit = AdminProbeAuditLog(
            job_id=job_id,
            offering_id=offering_id,
            model_id=model_id,
            provider_id=provider_id,
            triggered_by_admin_id=triggered_by_admin_id,
            success=success,
            status=status,
            error_code=error_code,
            ttft_ms=ttft_ms,
            e2e_latency_ms=e2e_latency_ms,
            throughput_tps=throughput_tps,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            probe_region=probe_region,
            started_at=started_at,
            finished_at=finished_at,
        )
        db.add(audit)
        await db.flush()
        await db.refresh(audit)
        return audit

    build_query = staticmethod(AdminProbeAuditRepository.build_query)

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        offering_id: Optional[int] = None,
        job_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[AdminProbeAuditLog]:
        return await AdminProbeAuditRepository.list(
            db,
            offering_id=offering_id,
            job_id=job_id,
            limit=limit,
        )
