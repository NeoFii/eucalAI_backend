"""Integration tests for POST /v1/anthropic/messages endpoint (RELAY-02).

Tests the full request chain for Anthropic Messages protocol.
Uses httpx AsyncClient with ASGITransport to test the actual FastAPI app.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest
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


def _mock_anthropic_response_data() -> dict:
    """Create mock Anthropic Messages response data."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from Claude!"}],
        "model": "claude-3-sonnet-20240229",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 8},
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_lifecycle_anthropic_non_stream():
    """Patch CallLifecycle.execute to return Anthropic format JSONResponse."""
    from fastapi.responses import JSONResponse

    response_data = _mock_anthropic_response_data()

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    return mock_execute


@pytest.fixture
def mock_lifecycle_anthropic_stream():
    """Patch CallLifecycle.execute to return Anthropic SSE stream."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            {"type": "message_start", "message": {"id": "msg_test123", "type": "message",
             "role": "assistant", "content": [], "model": "claude-3-sonnet-20240229",
             "usage": {"input_tokens": 10, "output_tokens": 0}}},
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "Hello!"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 5}},
            {"type": "message_stop"},
        ]
        for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    async def mock_execute(self):
        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    return mock_execute


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_messages_non_stream(mock_lifecycle_anthropic_non_stream):
    """POST /v1/anthropic/messages non-stream returns valid Anthropic format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_anthropic_non_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/anthropic/messages",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 100,
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert len(data["content"]) > 0
    assert data["content"][0]["type"] == "text"
    assert "usage" in data


@pytest.mark.asyncio
async def test_anthropic_messages_stream(mock_lifecycle_anthropic_stream):
    """POST /v1/anthropic/messages stream=true returns SSE format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_anthropic_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/anthropic/messages",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 100,
                    "stream": True,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: message_start" in body
    assert "event: content_block_delta" in body
    assert "event: message_stop" in body


@pytest.mark.asyncio
async def test_anthropic_messages_missing_max_tokens():
    """POST /v1/anthropic/messages without max_tokens returns 422."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/anthropic/messages",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    # max_tokens intentionally omitted
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anthropic_dual_path(mock_lifecycle_anthropic_non_stream):
    """POST /v1/anthropic/v1/messages is also reachable (dual path)."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_anthropic_non_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/anthropic/v1/messages",
                json={
                    "model": "claude-3-sonnet-20240229",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 100,
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    # Should not be 404 — route exists (either 200 or other non-404 status)
    assert resp.status_code != 404
