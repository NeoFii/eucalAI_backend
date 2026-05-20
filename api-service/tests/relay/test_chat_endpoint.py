"""Integration tests for POST /v1/chat/completions endpoint (RELAY-01).

Tests the full request chain: auth -> rate limit -> parse -> route -> upstream -> response.
Uses httpx AsyncClient with ASGITransport to test the actual FastAPI app.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.relay.auth import require_api_key
from app.relay.rate_limiter import require_rate_limit
from tests.relay.conftest import make_test_principal


# ── Override helpers ─────────────────────────────────────────────────────────


def _override_auth():
    principal = make_test_principal()

    async def _dep():
        return principal

    return principal, _dep


async def _noop_rate_limit():
    return None


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_completions_non_stream():
    """POST /v1/chat/completions non-stream returns valid OpenAI format."""
    from fastapi.responses import JSONResponse

    response_data = {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    principal, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("app.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello!"
    assert "usage" in data


@pytest.mark.asyncio
async def test_chat_completions_stream():
    """POST /v1/chat/completions stream=true returns SSE format."""
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
            _generate(), media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("app.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "data: " in body
    assert "data: [DONE]" in body


@pytest.mark.asyncio
async def test_chat_completions_invalid_model():
    """POST /v1/chat/completions with empty model returns 422."""
    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"Authorization": "Bearer sk-test123"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_completions_no_auth():
    """POST /v1/chat/completions without auth returns 401."""
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
        )

    assert resp.status_code == 401
