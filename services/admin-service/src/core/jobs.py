"""ARQ worker jobs for admin-service."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from arq.connections import RedisSettings
from arq.cron import cron

from core.config import settings
from core.db import close_db, create_engine, get_db_context, init_session_factory

logger = logging.getLogger(__name__)


def build_redis_settings(redis_url: str | None = None) -> RedisSettings:
    parsed = urlparse(redis_url or settings.ADMIN_QUEUE_REDIS_URL)
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
    from common.redis import init_redis
    await init_redis(settings.REDIS_URL)
    ctx["settings"] = settings
    logger.info("Admin worker started")


async def on_worker_shutdown(ctx: dict) -> None:
    del ctx
    from common.redis import close_redis
    await close_redis()
    await close_db()
    logger.info("Admin worker stopped")


async def check_channel_health(ctx: dict) -> None:
    from services.health_check_service import HealthCheckService
    async with get_db_context() as db:
        await HealthCheckService.run_health_checks(db)


def get_worker_settings_kwargs() -> dict:
    return {
        "functions": [check_channel_health],
        "cron_jobs": [
            cron(check_channel_health, minute={0, 10, 20, 30, 40, 50}),
        ],
        "redis_settings": build_redis_settings(),
        "max_jobs": settings.ADMIN_WORKER_CONCURRENCY,
        "job_timeout": settings.ADMIN_JOB_TIMEOUT_SECONDS,
        "on_startup": on_worker_startup,
        "on_shutdown": on_worker_shutdown,
    }
