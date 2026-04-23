"""Tests for VNext-B ConfigManager (router-service and inference-service)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from router_service.utils.runtime_config import build_default_runtime_config


def _make_admin_response(version: int = 1) -> Dict[str, Any]:
    """Build a realistic admin-service /active/full response."""
    return {
        "version": version,
        "status": "active",
        "router_alias": "auto",
        "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
        "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
        "score_bands": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
        "tier_model_map": {"1": "gpt-5-4", "2": "minimax-m2-7", "3": "qwen-3-5-397b-a17b", "4": "qwen3-5-flash", "5": "GLM4.7-Flash"},
        "model_providers": {
            "gpt-5-4": {"provider_slug": "openai", "api_key": "sk-test", "api_base": "https://api.openai.com", "upstream_model": "gpt-5-4"},
            "minimax-m2-7": {"provider_slug": "minimax", "api_key": "sk-mm", "api_base": "https://api.minimax.chat", "upstream_model": "minimax-m2-7"},
            "qwen-3-5-397b-a17b": {"provider_slug": "dashscope", "api_key": "sk-qw", "api_base": "https://dashscope.aliyuncs.com", "upstream_model": "qwen-3-5-397b-a17b"},
            "qwen3-5-flash": {"provider_slug": "dashscope", "api_key": "sk-qw2", "api_base": "https://dashscope.aliyuncs.com", "upstream_model": "qwen3-5-flash"},
            "GLM4.7-Flash": {"provider_slug": "zhipu", "api_key": "sk-glm", "api_base": "https://open.bigmodel.cn", "upstream_model": "GLM4.7-Flash"},
        },
    }


def _make_inference_admin_response(version: int = 1) -> Dict[str, Any]:
    """Build a realistic admin-service /active/inference response (no model_providers)."""
    return {
        "version": version,
        "status": "active",
        "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
        "weights": {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0},
        "score_bands": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
        "tier_model_map": {"1": "gpt-5-4", "2": "minimax-m2-7", "3": "qwen-3-5-397b-a17b", "4": "qwen3-5-flash", "5": "GLM4.7-Flash"},
    }


def _make_local_config_with_providers() -> Dict[str, Any]:
    cfg = build_default_runtime_config()
    cfg["model_providers"] = {
        "gpt-5-4": {"provider_slug": "openai", "api_key": "sk-local", "api_base": "https://api.openai.com", "upstream_model": "gpt-5-4"},
        "minimax-m2-7": {"provider_slug": "minimax", "api_key": "sk-local2", "api_base": "https://api.minimax.chat", "upstream_model": "minimax-m2-7"},
        "qwen-3-5-397b-a17b": {"provider_slug": "dashscope", "api_key": "sk-local3", "api_base": "https://dashscope.aliyuncs.com", "upstream_model": "qwen-3-5-397b-a17b"},
        "qwen3-5-flash": {"provider_slug": "dashscope", "api_key": "sk-local4", "api_base": "https://dashscope.aliyuncs.com", "upstream_model": "qwen3-5-flash"},
        "GLM4.7-Flash": {"provider_slug": "zhipu", "api_key": "sk-local5", "api_base": "https://open.bigmodel.cn", "upstream_model": "GLM4.7-Flash"},
    }
    return cfg


class FakeRouterSettings:
    admin_service_url = "http://127.0.0.1:8001"
    internal_secret = "test-secret"
    config_refresh_interval_seconds = 3600
    config_fetch_timeout_seconds = 5.0
    internal_http_max_retries = 1
    internal_http_retry_backoff_seconds = 0.2
    internal_http_circuit_breaker_threshold = 3
    internal_http_circuit_breaker_cooldown_seconds = 30.0


class FakeInferenceSettings:
    admin_service_url = "http://127.0.0.1:8001"
    internal_secret = "test-secret"
    config_refresh_interval_seconds = 3600
    config_fetch_timeout_seconds = 5.0


# ── Router ConfigManager tests ──


@pytest.fixture
def local_config_file(tmp_path):
    path = tmp_path / "runtime_config.json"
    path.write_text(json.dumps(_make_local_config_with_providers()), encoding="utf-8")
    return str(path)


from common.internal import InternalServiceResponseError, InternalServiceUnavailableError


# ── Finding 1: 403 fail fast + unavailable fallback tests ──


async def test_router_startup_403_fail_fast(local_config_file):
    from router_service.services.config_manager import ConfigManager

    exc = InternalServiceResponseError(
        "forbidden", target_service="admin-service",
        path="/active/full", status_code=403, detail="caller not allowed",
    )
    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=local_config_file)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, side_effect=exc):
        with pytest.raises(RuntimeError, match="rejected credentials"):
            await cm.start()


async def test_inference_startup_403_fail_fast(tmp_path):
    from inference_service.services.config_manager import ConfigManager

    cfg_path = tmp_path / "runtime_config.json"
    cfg_path.write_text(json.dumps(build_default_runtime_config()), encoding="utf-8")

    exc = InternalServiceResponseError(
        "forbidden", target_service="admin-service",
        path="/active/inference", status_code=403, detail="caller not allowed",
    )
    cm = ConfigManager(settings=FakeInferenceSettings(), runtime_config_path=str(cfg_path))
    with patch("inference_service.gateway.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, side_effect=exc):
        with pytest.raises(RuntimeError, match="rejected credentials"):
            await cm.start()


async def test_router_startup_unavailable_fallback_local(local_config_file):
    from router_service.services.config_manager import ConfigManager

    exc = InternalServiceUnavailableError(
        "connection refused", target_service="admin-service",
        path="/active/full",
    )
    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=local_config_file)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, side_effect=exc):
        await cm.start()
    try:
        assert cm.config_source == "local_fallback"
        assert cm.load() is not None
    finally:
        await cm.stop()


async def test_router_startup_admin_success(local_config_file):
    from router_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=local_config_file)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=_make_admin_response(version=5)):
        await cm.start()
    try:
        assert cm.config_source == "admin"
        assert cm.config_version == 5
        config = cm.load()
        assert config["tier_model_map"][3] == "qwen-3-5-397b-a17b"
        assert "gpt-5-4" in config["model_providers"]
    finally:
        await cm.stop()


async def test_router_startup_admin_404_fallback_local(local_config_file):
    from router_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=local_config_file)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=None):
        await cm.start()
    try:
        assert cm.config_source == "local_fallback"
        assert cm.config_version is None
        assert cm.load() is not None
    finally:
        await cm.stop()


async def test_router_startup_admin_error_fallback_local(local_config_file):
    from router_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=local_config_file)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, side_effect=Exception("connection refused")):
        await cm.start()
    try:
        assert cm.config_source == "local_fallback"
    finally:
        await cm.stop()


async def test_router_startup_both_fail_raises(tmp_path):
    from router_service.services.config_manager import ConfigManager

    nonexistent = str(tmp_path / "nonexistent.json")
    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=nonexistent)
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=None):
        with pytest.raises(RuntimeError):
            await cm.start()


# PLACEHOLDER_TESTS_2


async def test_router_startup_empty_providers_raises(tmp_path):
    from router_service.services.config_manager import ConfigManager

    cfg = build_default_runtime_config()
    path = tmp_path / "runtime_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    cm = ConfigManager(settings=FakeRouterSettings(), runtime_config_path=str(path))
    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=None):
        with pytest.raises(RuntimeError, match="no model_providers"):
            await cm.start()


async def test_router_refresh_updates_config(local_config_file):
    from router_service.services.config_manager import ConfigManager

    settings = FakeRouterSettings()
    settings.config_refresh_interval_seconds = 0.1
    cm = ConfigManager(settings=settings, runtime_config_path=local_config_file)

    call_count = 0
    async def _mock_fetch(_settings):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return _make_admin_response(version=10)

    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", side_effect=_mock_fetch):
        await cm.start()
        assert cm.config_source == "local_fallback"
        await asyncio.sleep(0.3)
        assert cm.config_source == "admin"
        assert cm.config_version == 10
    await cm.stop()


async def test_router_refresh_failure_keeps_cached(local_config_file):
    from router_service.services.config_manager import ConfigManager

    settings = FakeRouterSettings()
    settings.config_refresh_interval_seconds = 0.1
    cm = ConfigManager(settings=settings, runtime_config_path=local_config_file)

    call_count = 0
    async def _mock_fetch(_settings):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_admin_response(version=3)
        raise Exception("admin down")

    with patch("router_service.gateway_admin.AdminConfigGateway.fetch_active_config", side_effect=_mock_fetch):
        await cm.start()
        assert cm.config_source == "admin"
        assert cm.config_version == 3
        await asyncio.sleep(0.3)
        assert cm.config_source == "cached_previous"
        assert cm.config_version == 3
        assert cm.load() is not None
    await cm.stop()


# PLACEHOLDER_TESTS_3


# ── Inference ConfigManager tests ──


@pytest.fixture
def inference_local_config_file(tmp_path):
    cfg = build_default_runtime_config()
    path = tmp_path / "runtime_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


async def test_inference_startup_admin_success(inference_local_config_file):
    from inference_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeInferenceSettings(), runtime_config_path=inference_local_config_file)
    with patch("inference_service.gateway.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=_make_inference_admin_response(version=7)):
        await cm.start()
    try:
        assert cm.config_source == "admin"
        assert cm.config_version == 7
        config = cm.load()
        assert config["model_providers"] == {}
    finally:
        await cm.stop()


async def test_inference_startup_both_fail_raises(tmp_path):
    from inference_service.services.config_manager import ConfigManager

    nonexistent = str(tmp_path / "nonexistent.json")
    cm = ConfigManager(settings=FakeInferenceSettings(), runtime_config_path=nonexistent)
    with patch("inference_service.gateway.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=None):
        with pytest.raises(RuntimeError, match="failed to load"):
            await cm.start()


async def test_inference_normalize_strips_providers():
    from inference_service.utils.runtime_config import normalize_inference_config

    raw = _make_inference_admin_response()
    raw["model_providers"] = {"should": "be stripped"}
    raw["router_alias"] = "auto"
    result = normalize_inference_config(raw)
    assert result["model_providers"] == {}
    assert result["tier_model_map"][3] == "qwen-3-5-397b-a17b"


async def test_inference_local_fallback_no_env_vars(inference_local_config_file):
    from inference_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeInferenceSettings(), runtime_config_path=inference_local_config_file)
    with patch("inference_service.gateway.AdminConfigGateway.fetch_active_config", new_callable=AsyncMock, return_value=None):
        await cm.start()
    try:
        assert cm.config_source == "local_fallback"
        config = cm.load()
        assert config["model_providers"] == {}
    finally:
        await cm.stop()


async def test_inference_config_error_on_not_started():
    from inference_service.schemas.errors import InferenceConfigError
    from inference_service.services.config_manager import ConfigManager

    cm = ConfigManager(settings=FakeInferenceSettings(), runtime_config_path="/nonexistent")
    with pytest.raises(InferenceConfigError):
        cm.load()
