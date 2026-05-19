"""Three-tier rate limiter: global -> per-user -> per-key (D-13~D-18).

Token bucket algorithm via Redis Lua script with InMemory fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cachetools
from fastapi import Depends, Request

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_LUA_DIR = Path(__file__).parent / "lua"


class RateLimitExceeded(Exception):
    """Raised when a rate limit tier is exceeded."""

    def __init__(self, message: str, retry_after: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """Fallback when Redis is unavailable. Per-process, approximate."""

    def __init__(self) -> None:
        self._counters: cachetools.TTLCache[str, int] = cachetools.TTLCache(
            maxsize=4096, ttl=60,
        )

    def check(self, key: str, limit: int) -> bool:
        count = self._counters.get(key, 0)
        if count >= limit:
            return False
        self._counters[key] = count + 1
        return True


class RateLimiter:
    """Three-tier rate limiter: global -> per-user -> per-key.

    Uses Redis token bucket Lua script for precise rate limiting.
    Falls back to InMemoryRateLimiter when Redis is unavailable.
    """

    def __init__(
        self,
        *,
        redis: "aioredis.Redis | None",
        default_user_rpm: int = 20,
        global_rpm: int = 0,
    ) -> None:
        self._redis = redis
        self._default_user_rpm = default_user_rpm
        self._global_rpm = global_rpm
        self._fallback = InMemoryRateLimiter()
        self._token_bucket_script: Any = None

        if redis is not None:
            lua_path = _LUA_DIR / "token_bucket.lua"
            lua_src = lua_path.read_text()
            self._token_bucket_script = redis.register_script(lua_src)

    async def check_all(
        self,
        user_id: int,
        key_id: int,
        *,
        user_rpm: int | None = None,
        key_rpm: int | None = None,
    ) -> None:
        """Check all three tiers in order: global -> per-user -> per-key.

        Raises RateLimitExceeded if any tier is exceeded.
        """
        # Tier 1: Global limit
        if self._global_rpm > 0:
            allowed = await self._check("rl:global", self._global_rpm)
            if not allowed:
                raise RateLimitExceeded(
                    f"Global rate limit exceeded: {self._global_rpm} RPM",
                    retry_after=2,
                )

        # Tier 2: Per-user limit
        effective_user_rpm = user_rpm if user_rpm is not None else self._default_user_rpm
        if effective_user_rpm > 0:
            allowed = await self._check(f"rl:user:{user_id}", effective_user_rpm)
            if not allowed:
                raise RateLimitExceeded(
                    f"User rate limit exceeded: {effective_user_rpm} RPM",
                    retry_after=max(1, 60 // effective_user_rpm),
                )

        # Tier 3: Per-key limit (only if key_rpm is set)
        if key_rpm is not None and key_rpm > 0:
            allowed = await self._check(f"rl:key:{key_id}", key_rpm)
            if not allowed:
                raise RateLimitExceeded(
                    f"API key rate limit exceeded: {key_rpm} RPM",
                    retry_after=max(1, 60 // key_rpm),
                )

    async def _check(self, key: str, capacity: int) -> bool:
        """Run token bucket check via Redis Lua script, fallback to in-memory."""
        if self._redis is not None and self._token_bucket_script is not None:
            try:
                rate = capacity / 60.0  # tokens per second
                result = await self._token_bucket_script(
                    keys=[key],
                    args=[str(int(capacity)), str(rate), "1"],
                )
                return int(result) == 1
            except Exception:
                logger.debug(
                    "Redis token bucket failed, using in-memory fallback",
                    exc_info=True,
                )
        return self._fallback.check(key, capacity)


async def require_rate_limit(request: Request) -> None:
    """FastAPI dependency that enforces rate limiting on relay endpoints.

    Depends on require_api_key having already run (principal in request.state).
    """
    from api_service.core.config import settings
    from api_service.relay.dependencies import get_rate_limiter

    if not settings.RATE_LIMIT_ENABLED:
        return

    principal = request.state.principal
    rate_limiter = get_rate_limiter()

    await rate_limiter.check_all(
        user_id=principal.user_id,
        key_id=principal.id,
        user_rpm=principal.user_rpm_limit,
    )
