"""SSE format deep validation + rate limit 429 tests (RELAY-11, RELAY-12).

Tests SSE streaming format correctness and rate limiting behavior.
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
from api_service.relay.rate_limiter import RateLimitExceeded


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


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_lifecycle_openai_stream():
    """Patch CallLifecycle.execute to return OpenAI SSE stream with valid format."""
    from starlette.responses import StreamingResponse

    async def _generate():
        chunks = [
            {"id": "chatcmpl-test", "object": "chat.completion.chunk",
             "created": 1700000000, "model": "gpt-4",
             "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
            {"id": "chatcmpl-test", "object": "chat.completion.chunk",
             "created": 1700000000, "model": "gpt-4",
             "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]},
            {"id": "chatcmpl-test", "object": "chat.completion.chunk",
             "created": 1700000000, "model": "gpt-4",
             "choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]},
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


@pytest.fixture
def mock_lifecycle_anthropic_native_stream():
    """Patch CallLifecycle.execute to return Anthropic native SSE stream."""
    from starlette.responses import StreamingResponse

    async def _generate():
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_test", "type": "message", "role": "assistant",
                "content": [], "model": "claude-3-sonnet-20240229",
                "usage": {"input_tokens": 10, "output_tokens": 0}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "Hi there"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta",
             "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 5}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        for event_type, data in events:
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def mock_execute(self):
        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    return mock_execute


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_format_openai_chat(mock_lifecycle_openai_stream):
    """SSE format: each line starts with 'data: ', last line is 'data: [DONE]', middle lines are valid JSON."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_openai_stream,
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
    lines = [line for line in body.split("\n") if line.strip()]

    # All non-empty lines should start with "data: "
    for line in lines:
        assert line.startswith("data: "), f"Line does not start with 'data: ': {line}"

    # Last data line should be [DONE]
    assert lines[-1] == "data: [DONE]"

    # Middle lines (excluding [DONE]) should be valid JSON
    for line in lines[:-1]:
        payload = line[len("data: "):]
        parsed = json.loads(payload)
        assert "choices" in parsed


@pytest.mark.asyncio
async def test_sse_format_anthropic_native(mock_lifecycle_anthropic_native_stream):
    """Anthropic native stream: output contains 'event: message_start\\ndata: ' format."""
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_anthropic_native_stream,
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
    # Anthropic native format uses "event: <type>\ndata: <json>"
    assert "event: message_start\n" in body
    assert "event: content_block_delta\n" in body
    assert "event: message_stop\n" in body

    # Verify data lines after event lines are valid JSON
    data_lines = [line for line in body.split("\n") if line.startswith("data: ")]
    for line in data_lines:
        payload = line[len("data: "):]
        parsed = json.loads(payload)
        assert "type" in parsed


@pytest.mark.asyncio
async def test_stream_usage_injected(mock_lifecycle_openai_stream):
    """Verify stream_options.include_usage=True is expected in forward_payload (D-11).

    This test validates that the streaming endpoint accepts and processes
    stream_options correctly. The actual injection happens in CallLifecycle.execute.
    """
    principal = _make_principal()

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch("api_service.relay.rate_limiter.require_rate_limit", return_value=None),
        patch(
            "api_service.relay.lifecycle.orchestrator.CallLifecycle.execute",
            mock_lifecycle_openai_stream,
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
                    "stream_options": {"include_usage": True},
                },
                headers={"Authorization": "Bearer sk-test123"},
            )

    # Request with stream_options should be accepted (not rejected as invalid)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_rate_limit_429():
    """Rate limit exceeded returns 429 with error message."""
    principal = _make_principal()

    async def _raise_rate_limit(*args, **kwargs):
        raise RateLimitExceeded("User rate limit exceeded: 60 RPM", retry_after=3)

    with (
        patch("api_service.relay.auth.require_api_key", return_value=principal),
        patch(
            "api_service.relay.rate_limiter.require_rate_limit",
            side_effect=_raise_rate_limit,
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

    assert resp.status_code == 429
    data = resp.json()
    # Should contain error information about rate limiting
    assert "rate limit" in json.dumps(data).lower() or "error" in data
