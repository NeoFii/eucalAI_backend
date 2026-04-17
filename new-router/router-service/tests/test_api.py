"""Functional tests for API endpoints with mocked router engine."""

import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# We need to mock the heavy imports before importing the app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from router_service.logging import setup_logging
import tempfile

_log_dir = tempfile.mkdtemp()
setup_logging(log_dir=_log_dir)

import router_service.deps as deps_mod
from router_service.utils.runtime_config import normalize_runtime_config


# Build a test runtime config
TEST_RUNTIME_CONFIG = normalize_runtime_config({
    "router_alias": "auto",
    "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
    "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
    "score_bands": "0-5:3,5-10:1",
    "tier_model_map": {"1": "model-a", "2": "model-b", "3": "model-c", "4": "model-d", "5": "model-e"},
    "model_providers": {
        "model-a": {"provider_slug": "test", "api_key": "k", "api_base": "http://localhost:9999", "upstream_model": "m-a"},
        "model-b": {"provider_slug": "test", "api_key": "k", "api_base": "http://localhost:9999", "upstream_model": "m-b"},
        "model-c": {"provider_slug": "test", "api_key": "k", "api_base": "http://localhost:9999", "upstream_model": "m-c"},
        "model-d": {"provider_slug": "test", "api_key": "k", "api_base": "http://localhost:9999", "upstream_model": "m-d"},
        "model-e": {"provider_slug": "test", "api_key": "k", "api_base": "http://localhost:9999", "upstream_model": "m-e"},
    },
})


@pytest.fixture
def mock_runtime_store():
    store = MagicMock()
    store.load.return_value = TEST_RUNTIME_CONFIG
    return store


@pytest.fixture
def mock_router_engine():
    engine = MagicMock()
    engine.predict_chat_messages.return_value = {
        "request_id": "test-123",
        "scores_0_2": {"纠错": 0.5, "工具调用": 0.8, "通用任务": 0.6, "任务拆解": 0.7, "编程": 0.4},
        "proto_weighted_0_2": 0.6,
        "total_score_0_10": 3.0,
        "score_source": "proto_weighted_0_2",
        "routing_tier": 3,
        "selected_model": "model-c",
        "tier_model_map": TEST_RUNTIME_CONFIG["tier_model_map"],
        "score_bands_raw": TEST_RUNTIME_CONFIG["score_bands_raw"],
    }
    return engine


@pytest.fixture
def client(mock_runtime_store, mock_router_engine):
    deps_mod._runtime_store = mock_runtime_store
    deps_mod._router_engine = mock_router_engine

    from router_service.routers import chat, completions, meta
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(meta.router)
    app.include_router(chat.router)
    app.include_router(completions.router)

    with TestClient(app) as c:
        yield c

    deps_mod._runtime_store = None
    deps_mod._router_engine = None


class TestMetaEndpoints:
    def test_ready(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_models_requires_auth(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 401

    def test_models_with_auth(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        # First should be router alias
        assert data["data"][0]["id"] == "auto"

    def test_router_config(self, client):
        resp = client.get("/v1/router/config", headers={"Authorization": "Bearer test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["router_alias"] == "auto"
        assert "weights" in data
        assert "tier_model_map" in data


class TestChatCompletions:
    def test_unsupported_model(self, client):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "nonexistent", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 404

    @patch("router_service.routers.chat.litellm")
    def test_direct_model_call(self, mock_litellm, client):
        """Calling a known model directly (not router alias) should skip routing."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "resp-1",
            "object": "chat.completion",
            "model": "m-c",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
        }
        mock_litellm.completion.return_value = mock_response

        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "model-c", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        # v3: model field should be the selected model
        assert data["model"] == "model-c"
        # v3: no router field in response
        assert "router" not in data

    @patch("router_service.routers.chat.litellm")
    def test_routed_call(self, mock_litellm, client, mock_router_engine):
        """Calling with router alias should trigger routing."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "resp-2",
            "object": "chat.completion",
            "model": "m-c",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "routed response"}, "finish_reason": "stop"}],
        }
        mock_litellm.completion.return_value = mock_response

        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "auto", "messages": [{"role": "user", "content": "test"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        # v3: model = actual selected model, not router alias
        assert data["model"] == "model-c"
        # v3: no router data exposed
        assert "router" not in data
        # Router engine was called
        mock_router_engine.predict_chat_messages.assert_called_once()

    @patch("router_service.routers.chat.litellm")
    def test_response_headers(self, mock_litellm, client):
        """v3: only X-Router-Selected-Model and X-Router-Provider headers."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "resp-3",
            "object": "chat.completion",
            "model": "m-c",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        }
        mock_litellm.completion.return_value = mock_response

        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "auto", "messages": [{"role": "user", "content": "test"}]},
        )
        assert resp.status_code == 200
        assert "x-router-selected-model" in resp.headers
        assert "x-router-provider" in resp.headers
        # v3: no routing tier/score headers
        assert "x-demo5-routing-tier" not in resp.headers
        assert "x-demo5-total-score" not in resp.headers

    @patch("router_service.routers.chat.litellm")
    def test_think_tags_stripped(self, mock_litellm, client):
        """v3: <think> tags should be stripped from response content."""
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "resp-4",
            "object": "chat.completion",
            "model": "m-c",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "<think>reasoning</think>actual answer"}, "finish_reason": "stop"}],
        }
        mock_litellm.completion.return_value = mock_response

        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "model-c", "messages": [{"role": "user", "content": "test"}]},
        )
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "<think>" not in content
        assert "actual answer" in content
