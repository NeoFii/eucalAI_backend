"""Tests for RateLimiter three-tier rate limiting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.relay.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitExceeded,
    RateLimiter,
)


class TestInMemoryRateLimiter:
    def test_allows_under_limit(self):
        limiter = InMemoryRateLimiter()
        assert limiter.check("key1", 5) is True
        assert limiter.check("key1", 5) is True

    def test_blocks_at_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.check("key1", 5)
        assert limiter.check("key1", 5) is False


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_check_all_global_limit_exceeded(self):
        """Global RPM=1, second call should raise RateLimitExceeded."""
        # First check_all: global(1) + user(1) = 2 calls, both pass
        # Second check_all: global(0) = denied at global tier
        script_mock = AsyncMock(side_effect=[1, 1, 0])
        redis_mock = AsyncMock()
        redis_mock.register_script = MagicMock(return_value=script_mock)

        limiter = RateLimiter(redis=redis_mock, default_user_rpm=20, global_rpm=1)

        # First call passes
        await limiter.check_all(user_id=1, key_id=100)

        # Second call: global limit exceeded
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_all(user_id=1, key_id=100)
        assert "Global rate limit" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_check_all_passes_when_under_limit(self):
        """All limits generous — should pass without raising."""
        script_mock = AsyncMock(return_value=1)  # always allowed
        redis_mock = AsyncMock()
        redis_mock.register_script = MagicMock(return_value=script_mock)

        limiter = RateLimiter(redis=redis_mock, default_user_rpm=100, global_rpm=1000)
        # Should not raise
        await limiter.check_all(user_id=1, key_id=100)

    @pytest.mark.asyncio
    async def test_inmemory_fallback_when_redis_none(self):
        """When redis=None, uses InMemoryRateLimiter fallback."""
        limiter = RateLimiter(redis=None, default_user_rpm=2, global_rpm=0)

        # First two calls pass (user RPM=2)
        await limiter.check_all(user_id=1, key_id=100)
        await limiter.check_all(user_id=1, key_id=100)

        # Third call exceeds user limit
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_all(user_id=1, key_id=100)
        assert "User rate limit" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_check_order_global_first(self):
        """Verify global key is checked before user key."""
        call_keys: list[str] = []

        async def track_script(keys, args):
            call_keys.append(keys[0])
            return 1  # always allow

        script_mock = AsyncMock(side_effect=track_script)
        redis_mock = AsyncMock()
        redis_mock.register_script = MagicMock(return_value=script_mock)

        limiter = RateLimiter(redis=redis_mock, default_user_rpm=20, global_rpm=100)
        await limiter.check_all(user_id=42, key_id=7)

        # Global should be checked first, then user
        assert call_keys[0] == "rl:global"
        assert call_keys[1] == "rl:user:42"

    @pytest.mark.asyncio
    async def test_user_limit_exceeded_after_global_passes(self):
        """Global passes but user limit is exceeded."""
        call_count = 0

        async def script_fn(keys, args):
            nonlocal call_count
            call_count += 1
            # First call (global) passes, second call (user) fails
            if call_count == 1:
                return 1
            return 0

        script_mock = AsyncMock(side_effect=script_fn)
        redis_mock = AsyncMock()
        redis_mock.register_script = MagicMock(return_value=script_mock)

        limiter = RateLimiter(redis=redis_mock, default_user_rpm=20, global_rpm=100)
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_all(user_id=1, key_id=100)
        assert "User rate limit" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_per_key_limit_checked_when_provided(self):
        """Per-key RPM is checked as third tier when key_rpm is provided."""
        call_keys: list[str] = []

        async def track_script(keys, args):
            call_keys.append(keys[0])
            return 1

        script_mock = AsyncMock(side_effect=track_script)
        redis_mock = AsyncMock()
        redis_mock.register_script = MagicMock(return_value=script_mock)

        limiter = RateLimiter(redis=redis_mock, default_user_rpm=20, global_rpm=100)
        await limiter.check_all(user_id=1, key_id=55, key_rpm=10)

        assert "rl:global" in call_keys
        assert "rl:user:1" in call_keys
        assert "rl:key:55" in call_keys
