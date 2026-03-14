# -*- coding: utf-8 -*-
"""Benchmark job and admin probe audit services."""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from testing_service.models import AdminProbeAuditLog, BenchmarkJob

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
        result = await db.execute(select(BenchmarkJob).where(BenchmarkJob.job_id == job_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_total_offerings(db: AsyncSession, job_id: str, total_offerings: int) -> None:
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id)
            .values(total_offerings=total_offerings, updated_at=now())
        )

    @staticmethod
    async def mark_running(db: AsyncSession, job_id: str) -> None:
        started_at = now()
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id, BenchmarkJob.status == "queued")
            .values(status="running", started_at=started_at, updated_at=started_at)
        )

    @staticmethod
    async def mark_failed(db: AsyncSession, job_id: str, error_message: str) -> None:
        finished_at = now()
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id)
            .values(
                status="failed",
                error_message=error_message,
                finished_at=finished_at,
                updated_at=finished_at,
            )
        )

    @staticmethod
    async def mark_succeeded_empty(db: AsyncSession, job_id: str) -> None:
        finished_at = now()
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id)
            .values(status="succeeded", finished_at=finished_at, updated_at=finished_at)
        )

    @staticmethod
    async def record_child_result(
        db: AsyncSession,
        *,
        job_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> Optional[BenchmarkJob]:
        started_at = now()
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id)
            .values(
                status="running",
                started_at=func.coalesce(BenchmarkJob.started_at, started_at),
                completed_offerings=BenchmarkJob.completed_offerings + 1,
                succeeded_offerings=BenchmarkJob.succeeded_offerings + (1 if success else 0),
                failed_offerings=BenchmarkJob.failed_offerings + (0 if success else 1),
                error_message=error_message if error_message else BenchmarkJob.error_message,
                updated_at=started_at,
            )
        )
        job = await BenchmarkJobService.get_by_job_id(db, job_id)
        if job is None:
            return None
        if job.completed_offerings >= job.total_offerings:
            finished_at = now()
            final_status = "succeeded"
            if job.failed_offerings > 0 and job.succeeded_offerings > 0:
                final_status = "partial"
            elif job.failed_offerings > 0 and job.succeeded_offerings == 0:
                final_status = "failed"
            await db.execute(
                update(BenchmarkJob)
                .where(BenchmarkJob.job_id == job_id, BenchmarkJob.status.notin_(TERMINAL_JOB_STATUSES))
                .values(status=final_status, finished_at=finished_at, updated_at=finished_at)
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

    @staticmethod
    def build_query(
        *,
        offering_id: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Select:
        stmt: Select = select(AdminProbeAuditLog)
        if offering_id is not None:
            stmt = stmt.where(AdminProbeAuditLog.offering_id == offering_id)
        if job_id:
            stmt = stmt.where(AdminProbeAuditLog.job_id == job_id)
        return stmt.order_by(AdminProbeAuditLog.created_at.desc(), AdminProbeAuditLog.id.desc())

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        offering_id: Optional[int] = None,
        job_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[AdminProbeAuditLog]:
        stmt = AdminProbeAuditService.build_query(offering_id=offering_id, job_id=job_id).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
