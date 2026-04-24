"""Tests for ModelCatalogGateway with Redis caching integration."""

import json
import os
import sys

import pytest

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from common.internal import InternalServiceUnavailableError  # noqa: E402
from common.core.exceptions import ServiceUnavailableException  # noqa: E402
from user_service.gateway import ModelCatalogGateway  # noqa: E402


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self._store[key] = value


_VENDOR_RESPONSE = {
    "code": 200,
    "message": "success",
    "data": {"items": [{"id": 1, "slug": "openai", "name": "OpenAI"}], "total": 1, "page": 1, "page_size": 100},
}


class TestModelCatalogGatewayCaching:
    @pytest.fixture
    def gateway(self):
        return ModelCatalogGateway()

    @pytest.fixture
    def fake_redis(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("common.cache.get_cache_redis", lambda: fake)
        return fake

    @pytest.mark.asyncio
    async def test_cache_miss_calls_hmac_and_stores(self, gateway, fake_redis, monkeypatch):
        call_count = 0

        async def _mock_get_internal_json(**kwargs):
            nonlocal call_count
            call_count += 1
            return _VENDOR_RESPONSE

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        result = await gateway.list_vendors(page=1, page_size=100)
        assert result == _VENDOR_RESPONSE
        assert call_count == 1
        assert "mc:vendors:1:100" in fake_redis._store

    @pytest.mark.asyncio
    async def test_cache_hit_skips_hmac(self, gateway, fake_redis, monkeypatch):
        fake_redis._store["mc:vendors:1:100"] = json.dumps(_VENDOR_RESPONSE)
        call_count = 0

        async def _mock_get_internal_json(**kwargs):
            nonlocal call_count
            call_count += 1
            return {}

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        result = await gateway.list_vendors(page=1, page_size=100)
        assert result == _VENDOR_RESPONSE
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_to_direct_call(self, gateway, monkeypatch):
        def _raise():
            raise RuntimeError("Cache Redis not initialised")

        monkeypatch.setattr("common.cache.get_cache_redis", _raise)

        async def _mock_get_internal_json(**kwargs):
            return _VENDOR_RESPONSE

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        result = await gateway.list_vendors(page=1, page_size=100)
        assert result == _VENDOR_RESPONSE

    @pytest.mark.asyncio
    async def test_hmac_error_propagates_through_cache(self, gateway, fake_redis, monkeypatch):
        async def _mock_get_internal_json(**kwargs):
            raise InternalServiceUnavailableError(
                "admin-service down",
                target_service="admin-service",
                path="/api/v1/internal/model-catalog/vendors",
            )

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        with pytest.raises(ServiceUnavailableException):
            await gateway.list_vendors()

    @pytest.mark.asyncio
    async def test_list_models_cache_key_varies_by_params(self, gateway, fake_redis, monkeypatch):
        async def _mock_get_internal_json(**kwargs):
            return {"code": 200, "data": {"items": [], "total": 0, "page": 1, "page_size": 20}}

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        await gateway.list_models(page=1, page_size=20)
        await gateway.list_models(category="reasoning", page=1, page_size=20)

        keys = list(fake_redis._store.keys())
        assert len(keys) == 2
        assert keys[0] != keys[1]
        assert all(k.startswith("mc:models:") for k in keys)

    @pytest.mark.asyncio
    async def test_get_model_caches_by_slug(self, gateway, fake_redis, monkeypatch):
        detail = {"code": 200, "data": {"id": 1, "slug": "gpt-5", "name": "GPT-5"}}

        async def _mock_get_internal_json(**kwargs):
            return detail

        monkeypatch.setattr("user_service.gateway.get_internal_json", _mock_get_internal_json)

        result = await gateway.get_model("gpt-5")
        assert result == detail
        assert "mc:model:gpt-5" in fake_redis._store
