"""Tests for common.cache — Redis cache pool (db/2) and cache_get_or_fetch."""

import json
import os
import sys

import pytest

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from common.cache import cache_get_or_fetch  # noqa: E402


class _FakeRedis:
    """Minimal async Redis stub for testing."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self._store[key] = value


class _BrokenRedis(_FakeRedis):
    async def get(self, key: str):
        raise ConnectionError("redis down")

    async def set(self, key: str, value: str, *, ex: int | None = None):
        raise ConnectionError("redis down")


class TestCacheGetOrFetch:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self, monkeypatch):
        fake = _FakeRedis()
        payload = {"code": 200, "data": {"items": []}}
        fake._store["test:key"] = json.dumps(payload)
        monkeypatch.setattr("common.cache.get_cache_redis", lambda: fake)

        call_count = 0

        async def _fetch():
            nonlocal call_count
            call_count += 1
            return {"should": "not be called"}

        result = await cache_get_or_fetch("test:key", _fetch, ttl_seconds=60)
        assert result == payload
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_cache_miss_calls_fetch_and_stores(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("common.cache.get_cache_redis", lambda: fake)

        payload = {"code": 200, "data": {"items": [{"id": 1}]}}

        async def _fetch():
            return payload

        result = await cache_get_or_fetch("test:miss", _fetch, ttl_seconds=120)
        assert result == payload
        assert "test:miss" in fake._store
        assert json.loads(fake._store["test:miss"]) == payload

    @pytest.mark.asyncio
    async def test_redis_down_falls_through_to_fetch(self, monkeypatch):
        monkeypatch.setattr("common.cache.get_cache_redis", lambda: _BrokenRedis())

        payload = {"code": 200, "data": []}

        async def _fetch():
            return payload

        result = await cache_get_or_fetch("test:broken", _fetch, ttl_seconds=60)
        assert result == payload

    @pytest.mark.asyncio
    async def test_redis_not_initialised_falls_through(self, monkeypatch):
        def _raise():
            raise RuntimeError("Cache Redis not initialised")

        monkeypatch.setattr("common.cache.get_cache_redis", _raise)

        payload = {"code": 200}

        async def _fetch():
            return payload

        result = await cache_get_or_fetch("test:noinit", _fetch, ttl_seconds=60)
        assert result == payload

    @pytest.mark.asyncio
    async def test_fetch_exception_propagates(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("common.cache.get_cache_redis", lambda: fake)

        async def _fetch():
            raise ValueError("upstream error")

        with pytest.raises(ValueError, match="upstream error"):
            await cache_get_or_fetch("test:err", _fetch, ttl_seconds=60)

        assert "test:err" not in fake._store
