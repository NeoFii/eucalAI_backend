"""Tests for VNext-C router-service call-log integration in chat/completions handlers."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("INTERNAL_SECRET", "test_internal_secret_32chars_long!")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")

import pytest

from router_service.gateway import ValidatedApiKey
from router_service.gateway_calllog import CallLogGateway
from router_service.services.routing import RoutingError


_PRINCIPAL = ValidatedApiKey(id=10, user_id=42, name="test-key")

_ROUTE_META = {
    "config_version": 5,
    "config_source": "admin",
    "error_code": None,
    "inference_config_version": 3,
    "inference_config_source": "admin",
}

_TARGET_INFO = {
    "provider_slug": "openai",
    "upstream_model": "gpt-4",
    "api_key": "sk-test",
    "api_base": "https://api.openai.com",
}

_ROUTE_RESULT = {"routing_tier": 1, "score_source": "proto_weighted_0_2"}


def _fake_settings():
    return SimpleNamespace(
        user_service_url="http://localhost:8000",
        internal_secret="test_secret",
    )


def _mock_litellm_response(content="Hello!", tokens=None):
    usage = tokens or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    resp = MagicMock()
    resp.model_dump.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": usage,
    }
    return resp


# --- chat.py: non-stream success ---


@pytest.mark.asyncio
async def test_chat_nonstream_success_creates_and_updates_log():
    mock_create = AsyncMock(return_value={"id": 1, "request_id": "r1"})
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.chat.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.chat.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.chat.get_request_id", return_value="req-test"), \
         patch("router_service.routers.chat.route_and_resolve", new_callable=AsyncMock) as mock_route, \
         patch("router_service.routers.chat.litellm") as mock_litellm:

        mock_route.return_value = ("gpt-4", _TARGET_INFO, _ROUTE_RESULT, _ROUTE_META)
        mock_litellm.acompletion = AsyncMock(return_value=_mock_litellm_response())

        from router_service.routers.chat import chat_completions
        from router_service.schemas.requests import ChatCompletionRequest

        request = ChatCompletionRequest(
            model="auto",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
        raw_request = MagicMock()
        resp = await chat_completions(request, raw_request, _PRINCIPAL)

    mock_create.assert_called_once()
    create_kwargs = mock_create.call_args.kwargs
    assert create_kwargs["user_id"] == 42
    assert create_kwargs["status"] == 0

    assert mock_update.call_count == 2
    route_update = mock_update.call_args_list[0].kwargs
    assert route_update["selected_model"] == "gpt-4"
    assert route_update["provider_slug"] == "openai"

    final_update = mock_update.call_args_list[1].kwargs
    assert final_update["status"] == 1
    assert final_update["prompt_tokens"] == 10


# --- chat.py: upstream error ---


@pytest.mark.asyncio
async def test_chat_upstream_error_updates_log_status_2():
    mock_create = AsyncMock(return_value={"id": 1, "request_id": "r1"})
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.chat.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.chat.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.chat.get_request_id", return_value="req-err"), \
         patch("router_service.routers.chat.route_and_resolve", new_callable=AsyncMock) as mock_route, \
         patch("router_service.routers.chat.litellm") as mock_litellm:

        mock_route.return_value = ("gpt-4", _TARGET_INFO, _ROUTE_RESULT, _ROUTE_META)
        mock_litellm.acompletion = AsyncMock(side_effect=RuntimeError("upstream timeout"))

        from fastapi import HTTPException
        from router_service.routers.chat import chat_completions
        from router_service.schemas.requests import ChatCompletionRequest

        request = ChatCompletionRequest(
            model="auto",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
        with pytest.raises(HTTPException) as exc_info:
            await chat_completions(request, MagicMock(), _PRINCIPAL)
        assert exc_info.value.status_code == 502

    error_update = mock_update.call_args_list[-1].kwargs
    assert error_update["status"] == 2
    assert error_update["error_code"] == "upstream_error"


# --- chat.py: routing error ---


@pytest.mark.asyncio
async def test_chat_routing_error_updates_log():
    mock_create = AsyncMock(return_value={"id": 1, "request_id": "r1"})
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.chat.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.chat.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.chat.get_request_id", return_value="req-route"), \
         patch("router_service.routers.chat.route_and_resolve", new_callable=AsyncMock) as mock_route:

        mock_route.side_effect = RoutingError(404, error_code="model_not_found", detail="unsupported model: foo")

        from router_service.routers.chat import chat_completions
        from router_service.schemas.requests import ChatCompletionRequest

        request = ChatCompletionRequest(
            model="foo",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
        with pytest.raises(RoutingError):
            await chat_completions(request, MagicMock(), _PRINCIPAL)

    assert mock_update.call_count == 1
    update_kwargs = mock_update.call_args.kwargs
    assert update_kwargs["status"] == 2
    assert update_kwargs["error_code"] == "model_not_found"


# --- chat.py: create fails → skip all updates ---


@pytest.mark.asyncio
async def test_chat_create_fails_skips_updates():
    mock_create = AsyncMock(return_value=None)
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.chat.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.chat.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.chat.get_request_id", return_value="req-nolog"), \
         patch("router_service.routers.chat.route_and_resolve", new_callable=AsyncMock) as mock_route, \
         patch("router_service.routers.chat.litellm") as mock_litellm:

        mock_route.return_value = ("gpt-4", _TARGET_INFO, _ROUTE_RESULT, _ROUTE_META)
        mock_litellm.acompletion = AsyncMock(return_value=_mock_litellm_response())

        from router_service.routers.chat import chat_completions
        from router_service.schemas.requests import ChatCompletionRequest

        request = ChatCompletionRequest(
            model="auto",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
        )
        resp = await chat_completions(request, MagicMock(), _PRINCIPAL)

    mock_create.assert_called_once()
    mock_update.assert_not_called()


# --- completions.py: success ---


@pytest.mark.asyncio
async def test_completions_success_creates_and_updates_log():
    mock_create = AsyncMock(return_value={"id": 2, "request_id": "r2"})
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.completions.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.completions.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.completions.get_request_id", return_value="req-comp"), \
         patch("router_service.routers.completions.route_and_resolve", new_callable=AsyncMock) as mock_route, \
         patch("router_service.routers.completions.litellm") as mock_litellm:

        mock_route.return_value = ("gpt-4", _TARGET_INFO, _ROUTE_RESULT, _ROUTE_META)
        mock_litellm.acompletion = AsyncMock(return_value=_mock_litellm_response())

        from router_service.routers.completions import completions
        from router_service.schemas.requests import CompletionRequest

        request = CompletionRequest(model="auto", prompt="hello")
        resp = await completions(request, MagicMock(), _PRINCIPAL)

    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["is_stream"] is False
    assert mock_update.call_count == 2
    final_update = mock_update.call_args_list[-1].kwargs
    assert final_update["status"] == 1


# --- completions.py: routing error ---


@pytest.mark.asyncio
async def test_completions_routing_error_updates_log():
    mock_create = AsyncMock(return_value={"id": 3, "request_id": "r3"})
    mock_update = AsyncMock(return_value={"ok": True})

    with patch.object(CallLogGateway, "create_call_log", mock_create), \
         patch.object(CallLogGateway, "update_call_log", mock_update), \
         patch("router_service.routers.completions.get_settings", return_value=_fake_settings()), \
         patch("router_service.routers.completions.extract_client_ip", return_value="1.2.3.4"), \
         patch("router_service.routers.completions.get_request_id", return_value="req-comp-err"), \
         patch("router_service.routers.completions.route_and_resolve", new_callable=AsyncMock) as mock_route:

        mock_route.side_effect = RoutingError(503, error_code="no_fallback", detail="no fallback")

        from router_service.routers.completions import completions
        from router_service.schemas.requests import CompletionRequest

        request = CompletionRequest(model="auto", prompt="hello")
        with pytest.raises(RoutingError):
            await completions(request, MagicMock(), _PRINCIPAL)

    assert mock_update.call_count == 1
    assert mock_update.call_args.kwargs["error_code"] == "no_fallback"


# --- CallLogGateway best-effort: exceptions don't propagate ---


@pytest.mark.asyncio
async def test_gateway_create_swallows_exceptions():
    with patch("router_service.gateway_calllog.post_internal_json", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = RuntimeError("network error")
        result = await CallLogGateway.create_call_log(
            settings=_fake_settings(), request_id="r1", user_id=1, model_name="gpt-4",
        )
    assert result is None


@pytest.mark.asyncio
async def test_gateway_update_swallows_exceptions():
    with patch("router_service.gateway_calllog.patch_internal_json", new_callable=AsyncMock) as mock_patch:
        mock_patch.side_effect = RuntimeError("network error")
        result = await CallLogGateway.update_call_log(
            settings=_fake_settings(), request_id="r1", status=1,
        )
    assert result is None
