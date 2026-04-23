"""ARQ worker jobs for user-service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select

from common.utils.timezone import now
from user_service.config import settings
from user_service.db import close_db, create_engine, get_db_context, init_session_factory
from user_service.models import EmailVerificationCode
from user_service.services.usage_stat_service import UsageStatService

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
    create_engine(settings.DATABASE_URL)
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


def get_worker_settings_kwargs() -> dict:
    return {
        "functions": [
            aggregate_usage_stats,
            cleanup_expired_verification_codes,
        ],
        "cron_jobs": [
            cron(aggregate_usage_stats, minute=0),
            cron(cleanup_expired_verification_codes, hour=3, minute=0),
        ],
        "redis_settings": build_redis_settings(),
        "max_jobs": settings.USER_WORKER_CONCURRENCY,
        "job_timeout": settings.USER_JOB_TIMEOUT_SECONDS,
        "on_startup": on_worker_startup,
        "on_shutdown": on_worker_shutdown,
    }
