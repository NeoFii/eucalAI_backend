"""Integration tests for POST /v1/responses endpoint (RELAY-03).

Tests the full request chain for OpenAI Responses protocol.
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
async def test_responses_non_stream():
    """POST /v1/responses non-stream returns valid Responses format."""
    from fastapi.responses import JSONResponse

    response_data = {
        "id": "resp_test123", "object": "response", "created_at": 1700000000,
        "model": "gpt-4",
        "output": [{"type": "message", "id": "msg_test123", "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hello!"}]}],
        "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    }

    async def mock_execute(self):
        return JSONResponse(content=response_data)

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        with patch("app.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "gpt-4", "input": "hello", "stream": False},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert data["object"] == "response"
    assert len(data["output"]) > 0


@pytest.mark.asyncio
async def test_responses_stream():
    """POST /v1/responses stream=true returns SSE format."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            {"type": "response.created", "response": {"id": "resp_test123", "object": "response",
             "model": "gpt-4", "output": []}},
            {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": "Hello!"},
            {"type": "response.completed", "response": {"id": "resp_test123", "object": "response",
             "model": "gpt-4", "output": [{"type": "message", "id": "msg_test123", "role": "assistant",
             "content": [{"type": "output_text", "text": "Hello!"}]}],
             "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}}},
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
        with patch("app.relay.lifecycle.orchestrator.CallLifecycle.execute", mock_execute):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "gpt-4", "input": "hello", "stream": True},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: response.created" in body
    assert "event: response.completed" in body


@pytest.mark.asyncio
async def test_responses_invalid_request():
    """POST /v1/responses without model returns 422."""
    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _noop_rate_limit
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={"input": "hello", "stream": False},
                headers={"Authorization": "Bearer sk-test123"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422
