"""ARQ Redis pool — lifespan-managed accessor for enqueueing background jobs."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from api_service.common.observability import log_event
from api_service.core.config import settings

logger = logging.getLogger(__name__)

_arq_pool: ArqRedis | None = None


def _build_redis_settings() -> RedisSettings:
    """Parse settings.WORKER_QUEUE_REDIS_URL into arq RedisSettings."""
    parsed = urlparse(settings.WORKER_QUEUE_REDIS_URL)
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


async def init_arq_pool() -> None:
    """Initialize the ARQ Redis pool (called during lifespan startup)."""
    global _arq_pool
    _arq_pool = await create_pool(_build_redis_settings())
    log_event(logger, logging.INFO, "arqPoolInitialised")


async def close_arq_pool() -> None:
    """Close the ARQ Redis pool (called during lifespan shutdown)."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
        log_event(logger, logging.INFO, "arqPoolClosed")


def get_arq_pool() -> ArqRedis:
    """Return the initialised ARQ pool, or raise if unset."""
    if _arq_pool is None:
        raise RuntimeError("ARQ pool not initialised — call init_arq_pool() first")
    return _arq_pool
