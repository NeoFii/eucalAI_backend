"""Integration tests for POST /v1/chat/completions endpoint (RELAY-01).

Tests the full request chain: auth -> rate limit -> parse -> route -> upstream -> response.
Uses httpx AsyncClient with ASGITransport to test the actual FastAPI app.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api_service.relay.auth import ValidatedApiKey


def _make_principal() -> ValidatedApiKey:
    """Create a test ValidatedApiKey principal."""
    return ValidatedApiKey(
        id=1,
        user_id=1,
        key_hash="testhash123",
        status=1,
        quota_mode=0,
        quota_limit=0,
        quota_used=0,
        allowed_models="",
        allow_ips=None,
        expires_at=None,
        user_rpm_limit=60,
        balance=10000,
    )


def _mock_openai_response() -> MagicMock:
    """Create a mock non-streaming OpenAI response."""
    resp = MagicMock()
    resp.model_dump.return_value = {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return resp


async def _mock_stream_chunks() -> AsyncIterator:
    """Create a mock async iterator of OpenAI stream chunks."""
    chunks = [
        {"id": "chatcmpl-test123", "object": "chat.completion.chunk", "created": 1700000000,
         "model": "gpt-4", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {"id": "chatcmpl-test123", "object": "chat.completion.chunk", "created": 1700000000,
         "model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]},
        {"id": "chatcmpl-test123", "object": "chat.completion.chunk", "created": 1700000000,
         "model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "!"}, "finish_reason": None}]},
        {"id": "chatcmpl-test123", "object": "chat.completion.chunk", "created": 1700000000,
         "model": "gpt-4", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
    ]
    for chunk in chunks:
        mock_chunk = MagicMock()
        mock_chunk.model_dump.return_value = chunk
        yield mock_chunk


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_lifecycle_non_stream():
    """Patch CallLifecycle.execute to return a JSONResponse for non-stream."""
    from fastapi.responses import JSONResponse

    response_data = _mock_openai_response().model_dump()

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    return mock_execute


@pytest.fixture
def mock_lifecycle_stream():
    """Patch CallLifecycle.execute to return a StreamingResponse for stream."""
    from starlette.responses import StreamingResponse

    async def _generate():
        chunks = [
            {"id": "chatcmpl-test123", "object": "chat.completion.chunk",
             "model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}]},
            {"id": "chatcmpl-test123", "object": "chat.completion.chunk",
             "model": "gpt-4", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        for chunk in chunks:
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    async def mock_execute(self):
        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    return mock_execute


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_completions_non_stream(mock_lifecycle_non_stream):
    """POST /v1/chat/completions non-stream returns valid OpenAI format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_non_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello!"
    assert "usage" in data


@pytest.mark.asyncio
async def test_chat_completions_stream(mock_lifecycle_stream):
    """POST /v1/chat/completions stream=true returns SSE format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "data: " in body
    assert "data: [DONE]" in body


@pytest.mark.asyncio
async def test_chat_completions_invalid_model():
    """POST /v1/chat/completions with empty model returns 422."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_completions_no_auth():
    """POST /v1/chat/completions without auth returns 401."""
    from api_service.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )

    # Without auth header, require_api_key raises 401
    assert resp.status_code == 401
