"""Channel affinity: pin conversations to the same upstream channel.

Ported from router-service/src/services/channel_affinity.py.
Decision D-22: Redis key = affinity:{key}, TTL = 300s (CONTEXT.md overrides source 3600).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cachetools

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "affinity:"


class ChannelAffinityStore:
    """Redis-backed + in-memory LRU affinity store for channel pinning."""

    def __init__(
        self,
        *,
        redis: "aioredis.Redis | None",
        ttl: int = 300,
        lru_maxsize: int = 10000,
    ) -> None:
        self._redis = redis
        self._ttl = ttl
        self._cache: cachetools.TTLCache[str, str] = cachetools.TTLCache(
            maxsize=lru_maxsize, ttl=ttl,
        )

    async def get(self, affinity_key: str) -> str | None:
        """Get cached channel slug for an affinity key."""
        if self._redis is not None:
            try:
                val = await self._redis.get(f"{_KEY_PREFIX}{affinity_key}")
                if val is not None:
                    return str(val)
            except Exception:
                logger.debug("Redis affinity get failed, trying in-memory", exc_info=True)
        return self._cache.get(affinity_key)

    async def set(self, affinity_key: str, channel_slug: str) -> None:
        """Store channel slug for an affinity key."""
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


__all__ = ["ChannelAffinityStore"]
