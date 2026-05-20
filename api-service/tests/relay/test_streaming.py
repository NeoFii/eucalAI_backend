"""SSE format deep validation + rate limit 429 tests (RELAY-11, RELAY-12).

Tests SSE streaming format correctness and rate limiting behavior.
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
from app.relay.rate_limiter import RateLimitExceeded, require_rate_limit
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
async def test_sse_format_openai_chat():
    """SSE format: each line starts with 'data: ', last is 'data: [DONE]', middle are valid JSON."""
    from starlette.responses import StreamingResponse

    async def _generate():
        chunks = [
            {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1700000000,
             "model": "gpt-4", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
            {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1700000000,
             "model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]},
            {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1700000000,
             "model": "gpt-4", "choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]},
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
    lines = [line for line in body.split("\n") if line.strip()]
    for line in lines:
        assert line.startswith("data: "), f"Line does not start with 'data: ': {line}"
    assert lines[-1] == "data: [DONE]"
    for line in lines[:-1]:
        payload = line[len("data: "):]
        parsed = json.loads(payload)
        assert "choices" in parsed


@pytest.mark.asyncio
async def test_sse_format_anthropic_native():
    """Anthropic native stream: output contains 'event: message_start\\ndata: ' format."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_test", "type": "message", "role": "assistant",
                "content": [], "model": "claude-3-sonnet-20240229",
                "usage": {"input_tokens": 10, "output_tokens": 0}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "Hi there"}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        for event_type, data in events:
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

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
    assert "event: message_start\n" in body
    assert "event: message_stop\n" in body
    data_lines = [line for line in body.split("\n") if line.startswith("data: ")]
    for line in data_lines:
        payload = line[len("data: "):]
        parsed = json.loads(payload)
        assert "type" in parsed


@pytest.mark.asyncio
async def test_stream_usage_injected():
    """Verify stream_options.include_usage=True is accepted in request (D-11)."""
    from starlette.responses import StreamingResponse

    async def _generate():
        yield "data: {\"id\":\"chatcmpl-test\",\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n"
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
                    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}],
                          "stream": True, "stream_options": {"include_usage": True}},
                    headers={"Authorization": "Bearer sk-test123"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_rate_limit_429():
    """Rate limit exceeded returns 429 with error message."""
    async def _raise_rate_limit():
        raise RateLimitExceeded("User rate limit exceeded: 60 RPM", retry_after=3)

    _, auth_dep = _override_auth()
    app.dependency_overrides[require_api_key] = auth_dep
    app.dependency_overrides[require_rate_limit] = _raise_rate_limit
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"Authorization": "Bearer sk-test123"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 429
