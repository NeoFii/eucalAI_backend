"""Router module smoke tests."""

from __future__ import annotations

import os
import sys
import asyncio
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


class TestRouterConfig:
    """Router config tests."""

    def test_config_import(self):
        from router_service.config import settings

        assert settings is not None
        assert settings.PORT == 8003
        assert settings.SMART_ROUTER_ALIAS == "smart-router"


class TestRouterModels:
    """Router ORM model tests."""

    def test_router_api_key_model(self):
        from router_service.models import RouterAPIKey

        assert RouterAPIKey.__tablename__ == "router_api_keys"
        assert hasattr(RouterAPIKey, "owner_user_id")
        assert hasattr(RouterAPIKey, "key_hash")
        assert hasattr(RouterAPIKey, "key_ciphertext")
        assert hasattr(RouterAPIKey, "is_deleted")

    def test_router_billing_models(self):
        from sqlalchemy import UniqueConstraint

        from router_service.models import RouterBillingLedger, RouterUsageEvent

        assert RouterUsageEvent.__tablename__ == "router_usage_events"
        assert RouterBillingLedger.__tablename__ == "router_billing_ledger"
        assert not any(
            isinstance(constraint, UniqueConstraint) and {"usage_event_id"} == set(constraint.columns.keys())
            for constraint in RouterBillingLedger.__table__.constraints
        )


class TestRouterServices:
    """Router service helpers."""

    def test_generate_router_api_key(self):
        from router_service.services import RouterKeyAuthService

        raw_key = RouterKeyAuthService.generate_raw_key()
        assert raw_key.startswith("sk-eucal-")
        assert len(raw_key) > len("sk-eucal-")

    def test_encrypt_and_decrypt_router_api_key(self):
        from router_service.services import RouterKeyAuthService

        raw_key = "sk-eucal-test-secret"
        encrypted = RouterKeyAuthService._encrypt_raw_key(raw_key)
        decrypted = RouterKeyAuthService._decrypt_raw_key(encrypted)
        assert decrypted == raw_key

    def test_split_provider_prefix(self):
        from router_service.services import RoutingService

        provider, model = RoutingService.split_provider_prefix("openai:gpt-4.1")
        assert provider == "openai"
        assert model == "gpt-4.1"

        provider, model = RoutingService.split_provider_prefix("claude-3-7-sonnet")
        assert provider is None
        assert model == "claude-3-7-sonnet"

        provider, model = RoutingService.split_provider_prefix("meta-llama/Llama-3.1-8B-Instruct")
        assert provider is None
        assert model == "meta-llama/Llama-3.1-8B-Instruct"

    def test_cost_calculation(self):
        from router_service.services import RouterBillingService

        input_cost, output_cost, total_cost = RouterBillingService.calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            input_price_per_m=1.5,
            output_price_per_m=3.0,
        )
        assert input_cost == Decimal("0.001500")
        assert output_cost == Decimal("0.001500")
        assert total_cost == Decimal("0.003000")

    def test_smart_router_heuristic(self):
        from router_service.services.smart_router_service import SmartRouterService

        difficulty = SmartRouterService._heuristic(
            [{"role": "user", "content": "Need architecture and algorithm optimization"}]
        )
        assert difficulty >= 2

    @pytest.mark.asyncio
    async def test_provider_client_normalizes_full_chat_completions_url(self, monkeypatch):
        from router_service.services.provider_client_service import ProviderClientService

        captured = {}

        async def fake_acompletion(**kwargs):
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr("router_service.services.provider_client_service.litellm.acompletion", fake_acompletion)

        result = await ProviderClientService.chat_completion(
            model="/maas/deepseek-ai/DeepSeek-V3.2",
            messages=[{"role": "user", "content": "hello"}],
            api_key="secret",
            api_base="https://maas-api.lanyun.net/v1/chat/completions",
            stream=False,
            extra_payload={},
            timeout=30,
        )

        assert result == {"ok": True}
        assert captured["api_base"] == "https://maas-api.lanyun.net/v1"
        assert captured["base_url"] == "https://maas-api.lanyun.net/v1"
        assert captured["custom_llm_provider"] == "openai"


class TestRouterSchemas:
    """Router schema tests."""

    def test_model_list_response(self):
        from router_service.schemas import OpenAIModelCard, OpenAIModelListResponse

        response = OpenAIModelListResponse(data=[OpenAIModelCard(id="gpt-4.1")])
        assert response.object == "list"
        assert response.data[0].id == "gpt-4.1"

    def test_user_router_key_schema(self):
        from datetime import datetime

        from user_service.schemas import RouterApiKeyItem

        item = RouterApiKeyItem(
            id=1,
            name="default",
            token_preview="sk-eucal-1234",
            is_active=True,
            billing_mode="postpaid",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert item.name == "default"
        assert item.billing_mode == "postpaid"


class TestRouterAPI:
    """Router API import tests."""

    def test_router_api_imports(self):
        from router_service.api import api_router
        from router_service.main import app

        assert api_router is not None
        assert app is not None

    def test_router_key_endpoint_registered_on_router_service(self):
        from user_service.api.v1.router import api_router
        from router_service.api.v1.router import api_router as router_api_router

        user_route_paths = {route.path for route in api_router.routes}
        router_route_paths = {route.path for route in router_api_router.routes}
        assert "/api/v1/router/keys" not in user_route_paths
        assert "/api/v1/keys" in router_route_paths

    def test_start_services_registers_router(self):
        from scripts.start_services import SERVICES

        assert "router-service" in SERVICES
        assert SERVICES["router-service"]["app"] == "router_service.main:app"
        assert SERVICES["router-service"]["port"] == 8003


@pytest.mark.asyncio
async def test_invoke_chat_completion_records_failed_upstream_request(monkeypatch):
    from router_service.api.v1.endpoints import openai_compat
    from router_service.services import RouteCandidate, RouterKeyContext, RouterUpstreamError

    candidate = RouteCandidate(
        provider_slug="test-provider",
        provider_name="Test Provider",
        provider_model_name="provider/demo-model",
        api_base_url="https://example.com",
        encrypted_api_key=("cipher", "iv", "tag"),
        input_price_per_m=1.0,
        output_price_per_m=2.0,
    )
    context = RouterKeyContext(
        key_id=1,
        owner_user_id=2,
        name="default",
        key_hash="hash",
        billing_mode="postpaid",
        balance=None,
        daily_quota_tokens=None,
        monthly_quota_tokens=None,
        daily_quota_cost=None,
        monthly_quota_cost=None,
        rate_limit_rpm=60,
    )
    reserve_usage = AsyncMock()
    settle_usage = AsyncMock()

    monkeypatch.setattr(
        openai_compat,
        "_resolve_model_and_candidates",
        AsyncMock(return_value=("demo-model", [candidate], None)),
    )
    monkeypatch.setattr(
        openai_compat.RouterBillingService,
        "reserve_usage",
        reserve_usage,
    )
    monkeypatch.setattr(
        openai_compat.RouterBillingService,
        "settle_usage",
        settle_usage,
    )
    monkeypatch.setattr(
        openai_compat,
        "_decrypt_provider_key",
        AsyncMock(return_value="secret"),
    )
    monkeypatch.setattr(
        openai_compat.ProviderClientService,
        "chat_completion",
        AsyncMock(side_effect=RouterUpstreamError("provider down")),
    )
    monkeypatch.setattr(
        openai_compat,
        "get_settings",
        lambda: SimpleNamespace(ROUTER_STREAM_TIMEOUT_SECONDS=60),
    )

    with pytest.raises(HTTPException) as exc_info:
        await openai_compat._invoke_chat_completion(
            db=object(),
            context=context,
            request_payload={"messages": [{"role": "user", "content": "hello"}]},
            requested_model="demo-model",
            endpoint="/v1/chat/completions",
        )

    assert exc_info.value.status_code == 502
    reserve_usage.assert_awaited_once()
    settle_usage.assert_awaited_once()
    kwargs = settle_usage.await_args.kwargs
    assert kwargs["status_code"] == 502
    assert kwargs["provider_slug"] == "test-provider"
    assert kwargs["error_code"] == "upstream_error"
    assert kwargs["error_message"] == "provider down"


@pytest.mark.asyncio
async def test_release_stale_reservations_refunds_prepaid_balance(monkeypatch):
    from common.utils.timezone import now
    from router_service.services.billing_service import (
        PENDING_STATUS_CODE,
        RouterBillingService,
        STALE_PENDING_ERROR_CODE,
        STALE_PENDING_STATUS_CODE,
    )

    stale_event = SimpleNamespace(
        id=11,
        router_api_key_id=5,
        owner_user_id=9,
        endpoint="/v1/chat/completions",
        resolved_model="demo-model",
        usage_source="reserved",
        prompt_tokens=200,
        completion_tokens=400,
        total_tokens=600,
        cost_input=Decimal("0.100000"),
        cost_output=Decimal("0.200000"),
        cost_total=Decimal("0.300000"),
        status_code=PENDING_STATUS_CODE,
        error_code=None,
        error_message=None,
        latency_ms=123,
        created_at=now() - timedelta(minutes=10),
    )
    key_row = SimpleNamespace(
        billing_mode="prepaid",
        balance=Decimal("1.500000"),
    )
    added = []

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [stale_event]

    class FakeSession:
        async def execute(self, _statement):
            return FakeResult()

        def add(self, item):
            added.append(item)

        async def flush(self):
            return None

    monkeypatch.setattr(
        "router_service.services.billing_service.get_settings",
        lambda: SimpleNamespace(ROUTER_BILLING_CURRENCY="CNY"),
    )
    monkeypatch.setattr(
        RouterBillingService,
        "_lock_router_key",
        AsyncMock(return_value=key_row),
    )

    released = await RouterBillingService.release_stale_reservations(
        FakeSession(),
        max_age_seconds=300,
    )

    assert released == 1
    assert stale_event.status_code == STALE_PENDING_STATUS_CODE
    assert stale_event.error_code == STALE_PENDING_ERROR_CODE
    assert stale_event.total_tokens == 0
    assert stale_event.cost_total == Decimal("0")
    assert key_row.balance == Decimal("1.800000")
    assert len(added) == 1


@pytest.mark.asyncio
async def test_router_stale_reservation_sweeper_runs_periodically(monkeypatch):
    import router_service.main as router_main

    stop_event = asyncio.Event()
    releases = AsyncMock(return_value=2)
    logged = []
    waits = {"count": 0}

    async def fake_wait_for(awaitable, timeout):
        waits["count"] += 1
        assert timeout == 7
        if waits["count"] == 1:
            awaitable.close()
            raise asyncio.TimeoutError
        stop_event.set()
        return await awaitable

    monkeypatch.setattr(
        router_main,
        "settings",
        SimpleNamespace(
            ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS=7,
            ROUTER_PENDING_RESERVATION_MAX_AGE_SECONDS=300,
            SERVICE_NAME="router-service",
        ),
    )
    monkeypatch.setattr(router_main, "_release_stale_reservations_once", releases)
    monkeypatch.setattr(router_main, "_log_stale_release_result", lambda released: logged.append(released))
    monkeypatch.setattr(router_main.asyncio, "wait_for", fake_wait_for)

    await router_main._run_stale_reservation_sweeper(stop_event)

    releases.assert_awaited_once()
    assert logged == [2]


@pytest.mark.asyncio
async def test_router_stale_reservation_sweeper_is_disabled_when_interval_non_positive(monkeypatch):
    import router_service.main as router_main

    releases = AsyncMock()
    monkeypatch.setattr(
        router_main,
        "settings",
        SimpleNamespace(
            ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS=0,
            ROUTER_PENDING_RESERVATION_MAX_AGE_SECONDS=300,
            SERVICE_NAME="router-service",
        ),
    )
    monkeypatch.setattr(router_main, "_release_stale_reservations_once", releases)

    await router_main._run_stale_reservation_sweeper(asyncio.Event())

    releases.assert_not_awaited()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
