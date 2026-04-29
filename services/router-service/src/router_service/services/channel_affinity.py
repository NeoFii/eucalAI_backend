"""Channel affinity: pin conversations to the same upstream channel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cachetools

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger("router_service.affinity")

_KEY_PREFIX = "affinity:"


class ChannelAffinityStore:

    def __init__(
        self,
        *,
        redis: "aioredis.Redis | None",
        ttl: int = 3600,
        lru_maxsize: int = 10000,
    ) -> None:
        self._redis = redis
        self._ttl = ttl
        self._cache: cachetools.TTLCache[str, str] = cachetools.TTLCache(
            maxsize=lru_maxsize, ttl=ttl,
        )

    async def get(self, affinity_key: str) -> str | None:
        if self._redis is not None:
            try:
                val = await self._redis.get(f"{_KEY_PREFIX}{affinity_key}")
                if val is not None:
                    return str(val)
            except Exception:
                logger.debug("Redis affinity get failed, trying in-memory", exc_info=True)
        return self._cache.get(affinity_key)

    async def set(self, affinity_key: str, channel_slug: str) -> None:
        self._cache[affinity_key] = channel_slug
        if self._redis is not None:
            try:
                await self._redis.set(
                    f"{_KEY_PREFIX}{affinity_key}",
                    channel_slug,
                    ex=self._ttl,
                )
            except Exception:
                logger.debug("Redis affinity set failed", exc_info=True)
