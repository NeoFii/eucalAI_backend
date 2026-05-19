"""Integration tests for POST /v1/anthropic/messages endpoint (RELAY-02).

Tests the full request chain for Anthropic Messages protocol.
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

from api_service.main import app
from api_service.relay.auth import require_api_key
from api_service.relay.rate_limiter import require_rate_limit
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
async def test_anthropic_messages_non_stream():
    """POST /v1/anthropic/messages non-stream returns valid Anthropic format."""
    from fastapi.responses import JSONResponse

    response_data = {
        "id": "msg_test123", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "Hello from Claude!"}],
        "model": "claude-3-sonnet-20240229", "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 8},
    }

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("api_service.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/anthropic/messages",
                    json={"model": "claude-3-sonnet-20240229", "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 100, "stream": False},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert len(data["content"]) > 0
    assert data["content"][0]["type"] == "text"
    assert "usage" in data


@pytest.mark.asyncio
async def test_anthropic_messages_stream():
    """POST /v1/anthropic/messages stream=true returns SSE format."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            {"type": "message_start", "message": {"id": "msg_test123", "type": "message",
             "role": "assistant", "content": [], "model": "claude-3-sonnet-20240229",
             "usage": {"input_tokens": 10, "output_tokens": 0}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello!"}},
            {"type": "message_stop"},
        ]
        for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    async def mock_execute(self):
        return StreamingResponse(
            _generate(), media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("api_service.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/anthropic/messages",
                    json={"model": "claude-3-sonnet-20240229", "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 100, "stream": True},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: message_start" in body
    assert "event: message_stop" in body


@pytest.mark.asyncio
async def test_anthropic_messages_missing_max_tokens():
    """POST /v1/anthropic/messages without max_tokens returns 422."""
    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/anthropic/messages",
                json={"model": "claude-3-sonnet-20240229", "messages": [{"role": "user", "content": "hi"}],
                      "stream": False},
                headers={"Authorization": "Bearer sk-test123"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anthropic_dual_path():
    """POST /v1/anthropic/v1/messages is also reachable (dual path)."""
    from fastapi.responses import JSONResponse

    response_data = {
        "id": "msg_test123", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "Hello!"}],
        "model": "claude-3-sonnet-20240229", "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("api_service.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/anthropic/v1/messages",
                    json={"model": "claude-3-sonnet-20240229", "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 100, "stream": False},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code != 404
