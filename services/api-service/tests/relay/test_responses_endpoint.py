"""Integration tests for POST /v1/responses endpoint (RELAY-03).

Tests the full request chain for OpenAI Responses protocol.
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


def _mock_responses_data() -> dict:
    """Create mock OpenAI Responses format data."""
    return {
        "id": "resp_test123",
        "object": "response",
        "created_at": 1700000000,
        "model": "gpt-4",
        "output": [
            {
                "type": "message",
                "id": "msg_test123",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello!"}],
            }
        ],
        "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_lifecycle_responses_non_stream():
    """Patch CallLifecycle.execute to return Responses format JSONResponse."""
    from fastapi.responses import JSONResponse

    response_data = _mock_responses_data()

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    return mock_execute


@pytest.fixture
def mock_lifecycle_responses_stream():
    """Patch CallLifecycle.execute to return Responses SSE stream."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            {"type": "response.created", "response": {"id": "resp_test123",
             "object": "response", "model": "gpt-4", "output": []}},
            {"type": "response.output_item.added", "output_index": 0,
             "item": {"type": "message", "id": "msg_test123", "role": "assistant", "content": []}},
            {"type": "response.content_part.added", "output_index": 0, "content_index": 0,
             "part": {"type": "output_text", "text": ""}},
            {"type": "response.output_text.delta", "output_index": 0, "content_index": 0,
             "delta": "Hello!"},
            {"type": "response.output_text.done", "output_index": 0, "content_index": 0,
             "text": "Hello!"},
            {"type": "response.completed", "response": {"id": "resp_test123",
             "object": "response", "model": "gpt-4",
             "output": [{"type": "message", "id": "msg_test123", "role": "assistant",
                         "content": [{"type": "output_text", "text": "Hello!"}]}],
             "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}}},
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
async def test_responses_non_stream(mock_lifecycle_responses_non_stream):
    """POST /v1/responses non-stream returns valid Responses format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_responses_non_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={
                    "model": "gpt-4",
                    "input": "hello",
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert data["object"] == "response"
    assert len(data["output"]) > 0


@pytest.mark.asyncio
async def test_responses_stream(mock_lifecycle_responses_stream):
    """POST /v1/responses stream=true returns SSE format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_responses_stream,
        ),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={
                    "model": "gpt-4",
                    "input": "hello",
                    "stream": True,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: response.created" in body
    assert "event: response.completed" in body


@pytest.mark.asyncio
async def test_responses_invalid_request():
    """POST /v1/responses without model returns 422."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
    ):
        from api_service.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={
                    # model intentionally omitted
                    "input": "hello",
                    "stream": False,
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    assert resp.status_code == 422
