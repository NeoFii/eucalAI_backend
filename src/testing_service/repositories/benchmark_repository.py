"""Benchmark job and probe audit data access."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.timezone import now
from testing_service.models import AdminProbeAuditLog, BenchmarkJob


class BenchmarkJobRepository:
    """Data access for benchmark dispatch jobs."""

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
    async def increment_child_result(
        db: AsyncSession,
        *,
        job_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
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

    @staticmethod
    async def mark_terminal_if_incomplete(
        db: AsyncSession,
        *,
        job_id: str,
        final_status: str,
        terminal_statuses: set[str],
    ) -> None:
        finished_at = now()
        await db.execute(
            update(BenchmarkJob)
            .where(BenchmarkJob.job_id == job_id, BenchmarkJob.status.notin_(terminal_statuses))
            .values(status=final_status, finished_at=finished_at, updated_at=finished_at)
        )


class AdminProbeAuditRepository:
    """Data access for manual probe audit rows."""

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
        stmt = AdminProbeAuditRepository.build_query(
            offering_id=offering_id,
            job_id=job_id,
        ).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
