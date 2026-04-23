"""Tests for VNext-B router-service fallback logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from router_service.services.inference_client import ClassifyResult


def _make_config() -> Dict[str, Any]:
    return {
        "router_alias": "auto",
        "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
        "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
        "score_bands_raw": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
        "score_bands": [(0, 3, 5), (3, 5, 4), (5, 7, 3), (7, 9, 2), (9, 10, 1)],
        "tier_model_map": {1: "gpt-5-4", 2: "minimax-m2-7", 3: "qwen-3-5-397b-a17b", 4: "qwen3-5-flash", 5: "GLM4.7-Flash"},
        "model_providers": {
            "gpt-5-4": {"provider_slug": "openai", "api_key": "sk-test", "api_base": "https://api.openai.com", "upstream_model": "gpt-5-4"},
            "qwen-3-5-397b-a17b": {"provider_slug": "dashscope", "api_key": "sk-qw", "api_base": "https://dashscope.aliyuncs.com", "upstream_model": "qwen-3-5-397b-a17b"},
        },
    }


class FakeConfigManager:
    def __init__(self, config=None):
        self._config = config or _make_config()
        self.config_version = 5
        self.config_source = "admin"

    def load(self):
        return self._config


def _success_classify_result() -> ClassifyResult:
    return ClassifyResult(
        success=True,
        data={
            "selected_model": "gpt-5-4",
            "scores_0_2": {"纠错": 1.5, "工具调用": 0.8, "通用任务": 0.5, "任务拆解": 0.3, "编程": 0.2},
            "total_score_0_10": 8.5,
            "score_source": "proto_weighted_0_2",
            "routing_tier": 1,
            "fallback_routes": [],
        },
    )


async def test_inference_unavailable_fallback_tier3():
    from router_service.services.routing import route_and_resolve

    fake_cm = FakeConfigManager()
    fake_client = AsyncMock()
    fake_client.classify.return_value = ClassifyResult(
        success=False, error_code="unavailable", error_message="service down"
    )

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        selected, target, result, meta = await route_and_resolve(
            requested_model="auto",
            messages=[{"role": "user", "content": "hello"}],
            request_id="test-123",
        )
    assert selected == "qwen-3-5-397b-a17b"
    assert meta["error_code"] == "unavailable"


async def test_inference_auth_error_returns_502():
    from router_service.services.routing import route_and_resolve

    fake_cm = FakeConfigManager()
    fake_client = AsyncMock()
    fake_client.classify.return_value = ClassifyResult(
        success=False, error_code="auth", error_message="forbidden"
    )

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await route_and_resolve(
                requested_model="auto",
                messages=[{"role": "user", "content": "hello"}],
                request_id="test-123",
            )
    assert exc_info.value.status_code == 502


async def test_inference_validation_error_returns_400():
    from router_service.services.routing import route_and_resolve

    fake_cm = FakeConfigManager()
    fake_client = AsyncMock()
    fake_client.classify.return_value = ClassifyResult(
        success=False, error_code="validation", error_message="bad input"
    )

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await route_and_resolve(
                requested_model="auto",
                messages=[{"role": "user", "content": "hello"}],
                request_id="test-123",
            )
    assert exc_info.value.status_code == 400


async def test_fallback_no_tier3_returns_503():
    from router_service.services.routing import route_and_resolve

    config = _make_config()
    del config["model_providers"]["qwen-3-5-397b-a17b"]
    fake_cm = FakeConfigManager(config=config)
    fake_client = AsyncMock()
    fake_client.classify.return_value = ClassifyResult(
        success=False, error_code="unavailable", error_message="down"
    )

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await route_and_resolve(
                requested_model="auto",
                messages=[{"role": "user", "content": "hello"}],
                request_id="test-123",
            )
    assert exc_info.value.status_code == 503


async def test_successful_classify_returns_4tuple():
    from router_service.services.routing import route_and_resolve

    fake_cm = FakeConfigManager()
    fake_client = AsyncMock()
    fake_client.classify.return_value = _success_classify_result()

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        selected, target, result, meta = await route_and_resolve(
            requested_model="auto",
            messages=[{"role": "user", "content": "hello"}],
            request_id="test-123",
        )
    assert selected == "gpt-5-4"
    assert meta["config_version"] == 5
    assert meta["config_source"] == "admin"
    assert meta["error_code"] is None


async def test_circuit_open_fallback_tier3():
    from router_service.services.routing import route_and_resolve

    fake_cm = FakeConfigManager()
    fake_client = AsyncMock()
    fake_client.classify.return_value = ClassifyResult(
        success=False, error_code="circuit_open", error_message="breaker open"
    )

    with patch("router_service.services.routing.get_config_manager", return_value=fake_cm), \
         patch("router_service.services.routing.get_inference_client", return_value=fake_client):
        selected, target, result, meta = await route_and_resolve(
            requested_model="auto",
            messages=[{"role": "user", "content": "hello"}],
            request_id="test-123",
        )
    assert selected == "qwen-3-5-397b-a17b"
    assert meta["error_code"] == "circuit_open"
