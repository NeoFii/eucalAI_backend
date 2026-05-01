"""Three-tier rate limiter: global → user → pool account."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

import cachetools

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger("router_service.rate_limiter")

_LUA_DIR = Path(__file__).parent / "lua"


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int = 1):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """Fallback when Redis is unavailable. Per-process, approximate."""

    def __init__(self) -> None:
        self._counters: cachetools.TTLCache[str, int] = cachetools.TTLCache(
            maxsize=50000, ttl=60,
        )

    def check(self, key: str, limit: int) -> bool:
        count = self._counters.get(key, 0)
        if count >= limit:
            return False
        self._counters[key] = count + 1
        return True

    def current_count(self, key: str) -> int:
        return self._counters.get(key, 0)


class RateLimiter:

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
        self._sliding_window_script: Any = None
        self._token_bucket_script: Any = None

        if redis is not None:
            sw_lua = (_LUA_DIR / "sliding_window.lua").read_text()
            tb_lua = (_LUA_DIR / "token_bucket.lua").read_text()
            self._sliding_window_script = redis.register_script(sw_lua)
            self._token_bucket_script = redis.register_script(tb_lua)

    async def check_global(self) -> None:
        if self._global_rpm <= 0:
            return
        allowed = await self._sliding_window_check("rl:global", self._global_rpm)
        if not allowed:
            raise RateLimitExceeded(
                f"Global rate limit exceeded: {self._global_rpm} requests per minute.",
                retry_after=2,
            )

    async def check_user(self, user_id: int, rpm_override: int | None = None) -> None:
        limit = rpm_override if rpm_override is not None else self._default_user_rpm
        if limit <= 0:
            return
        key = f"rl:user:{user_id}"
        allowed = await self._token_bucket_check(key, capacity=limit, rate=limit / 60.0)
        if not allowed:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {limit} requests per minute.",
                retry_after=max(1, 60 // limit),
            )

    async def check_account(self, account_id: int, rpm_limit: int | None) -> bool:
        if rpm_limit is None or rpm_limit <= 0:
            return True
        key = f"rl:acct:{account_id}"
        return await self._sliding_window_check(key, rpm_limit)

    async def is_account_available(self, account_id: int, rpm_limit: int | None) -> bool:
        if rpm_limit is None or rpm_limit <= 0:
            return True
        key = f"rl:acct:{account_id}"
        if self._redis is not None:
            try:
                now = time.time()
                window_start = now - 60
                count = await self._redis.zcount(key, window_start, "+inf")
                return count < rpm_limit
            except Exception:
                return self._fallback.current_count(key) < rpm_limit
        return self._fallback.current_count(key) < rpm_limit

    async def _sliding_window_check(self, key: str, limit: int) -> bool:
        if self._redis is not None and self._sliding_window_script is not None:
            try:
                now = time.time()
                window_start = now - 60
                result = await self._sliding_window_script(
                    keys=[key],
                    args=[str(window_start), str(now), str(limit), "120"],
                )
                return int(result) == 1
            except Exception:
                logger.debug("Redis sliding window failed, using in-memory fallback", exc_info=True)
        return self._fallback.check(key, limit)

    async def _token_bucket_check(self, key: str, capacity: float, rate: float) -> bool:
        if self._redis is not None and self._token_bucket_script is not None:
            try:
                result = await self._token_bucket_script(
                    keys=[key],
                    args=[str(int(capacity)), str(rate), "1"],
                )
                return int(result) == 1
            except Exception:
                logger.debug("Redis token bucket failed, using in-memory fallback", exc_info=True)
        return self._fallback.check(key, int(capacity))
