"""Dedicated Redis cache pool (db/2) with fail-open get-or-fetch helper."""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_cache_redis: aioredis.Redis | None = None


async def init_cache_redis(url: str) -> None:
    global _cache_redis
    _cache_redis = aioredis.from_url(url, decode_responses=True)
    await _cache_redis.ping()


def get_cache_redis() -> aioredis.Redis:
    if _cache_redis is None:
        raise RuntimeError("Cache Redis not initialised — call init_cache_redis() first")
    return _cache_redis


async def close_cache_redis() -> None:
    global _cache_redis
    if _cache_redis is not None:
        await _cache_redis.aclose()
        _cache_redis = None


async def check_cache_redis_ready() -> tuple[bool, str | None]:
    if _cache_redis is None:
        return False, "Cache Redis not initialised"
    try:
        await _cache_redis.ping()
        return True, None
    except Exception as exc:
        return False, str(exc)


async def cache_get_or_fetch(
    key: str,
    fetch: Callable[..., Awaitable[dict | list]],
    ttl_seconds: int,
) -> dict | list:
    try:
        r = get_cache_redis()
        cached = await r.get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception:
        logger.debug("cache read failed for %s, falling through to fetch", key)

    result = await fetch()

    try:
        r = get_cache_redis()
        await r.set(key, json.dumps(result, ensure_ascii=False), ex=ttl_seconds)
    except Exception:
        logger.debug("cache write failed for %s", key)

    return result
