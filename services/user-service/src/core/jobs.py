"""ARQ worker jobs for user-service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, text

from common.observability import log_event
from common.utils.timezone import now
from core.config import settings
from core.db import close_db, create_engine, get_db_context, init_session_factory
from models import EmailVerificationCode
from services.usage_stat_service import UsageStatService

logger = logging.getLogger(__name__)


def build_redis_settings(redis_url: str | None = None) -> RedisSettings:
    parsed = urlparse(redis_url or settings.USER_QUEUE_REDIS_URL)
    database = 0
    path = (parsed.path or "").lstrip("/")
    if path:
        database = int(path)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


async def on_worker_startup(ctx: dict) -> None:
    create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    )
    init_session_factory()
    ctx["settings"] = settings
    logger.info("User worker started")


async def on_worker_shutdown(ctx: dict) -> None:
    del ctx
    await close_db()
    logger.info("User worker stopped")


async def aggregate_usage_stats(ctx: dict, stat_hour_iso: str | None = None) -> None:
    del ctx
    if stat_hour_iso:
        stat_hour = datetime.fromisoformat(stat_hour_iso)
    else:
        stat_hour = now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    async with get_db_context() as db:
        await UsageStatService.aggregate_hour(db, stat_hour)


async def cleanup_expired_verification_codes(ctx: dict) -> None:
    del ctx
    cutoff = now() - timedelta(days=settings.VERIFICATION_CODE_RETENTION_DAYS)
    async with get_db_context() as db:
        records = list(
            (
                await db.execute(
                    select(EmailVerificationCode).where(
                        EmailVerificationCode.expires_at < cutoff,
                        EmailVerificationCode.used_at.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for record in records:
            await db.delete(record)
        await db.commit()


async def cleanup_expired_sessions(ctx: dict) -> None:
    """Remove sessions expired more than 7 days ago."""
    del ctx
    cutoff = now() - timedelta(days=7)
    async with get_db_context() as db:
        await db.execute(
            text("DELETE FROM user_sessions WHERE expires_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
    logger.info("Cleaned up expired sessions older than %s", cutoff)


async def reconcile_balance_ledger(ctx: dict) -> None:
    """Daily reconciliation: detect drift between users.balance and ledger sum."""
    del ctx
    async with get_db_context() as db:
        result = await db.execute(text("""
            SELECT u.id, u.uid, u.balance, COALESCE(SUM(bt.amount), 0) AS tx_sum
            FROM users u
            LEFT JOIN balance_transactions bt ON bt.user_id = u.id
            GROUP BY u.id, u.uid, u.balance
            HAVING u.balance != COALESCE(SUM(bt.amount), 0)
        """))
        drifted = result.all()
        if drifted:
            for row in drifted:
                log_event(
                    logger, "ERROR", "balanceDrift",
                    user_id=row.id, uid=row.uid,
                    balance=row.balance, tx_sum=row.tx_sum,
                    delta=row.balance - row.tx_sum,
                )
        else:
            logger.info("Balance reconciliation passed: no drift detected")


def get_worker_settings_kwargs() -> dict:
    return {
        "functions": [
            aggregate_usage_stats,
            cleanup_expired_verification_codes,
            cleanup_expired_sessions,
            reconcile_balance_ledger,
        ],
        "cron_jobs": [
            cron(aggregate_usage_stats, minute=0),
            cron(cleanup_expired_verification_codes, hour=3, minute=0),
            cron(cleanup_expired_sessions, hour=3, minute=30),
            cron(reconcile_balance_ledger, hour=4, minute=30),
        ],
        "redis_settings": build_redis_settings(),
        "max_jobs": settings.USER_WORKER_CONCURRENCY,
        "job_timeout": settings.USER_JOB_TIMEOUT_SECONDS,
        "on_startup": on_worker_startup,
        "on_shutdown": on_worker_shutdown,
    }
