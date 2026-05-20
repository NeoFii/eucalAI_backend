"""Application-wide Redis connection pool."""

from __future__ import annotations

import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None


async def init_redis(url: str) -> None:
    global _redis
    _redis = aioredis.from_url(url, decode_responses=True)
    await _redis.ping()


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def check_redis_ready() -> tuple[bool, str | None]:
    """Probe Redis connectivity. Returns (ok, error_message)."""
    if _redis is None:
        return False, "Redis not initialised"
    try:
        await _redis.ping()
        return True, None
    except Exception as exc:
        return False, str(exc)
