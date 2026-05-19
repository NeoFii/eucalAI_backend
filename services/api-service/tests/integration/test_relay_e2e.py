"""E2E relay flow integration tests — 3 protocols x stream/non-stream.

Tests the full relay lifecycle: auth -> route -> forward -> bill -> log.
Requires real DB, Redis, and inference-service at localhost:8004.

These tests use ASGITransport which buffers the full response body,
so SSE streaming tests parse resp.text as a complete body.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from api_service.models.api_call_log import ApiCallLog
from tests.integration.conftest import TEST_API_KEY_RAW


AUTH_HEADER = {"Authorization": f"Bearer {TEST_API_KEY_RAW}"}


@pytest.mark.asyncio
class TestRelayE2E:
    """End-to-end relay flow tests for all 3 protocols."""

    # ──────────────────────────────────────────────────────────────────────
    # OpenAI Chat Completions
    # ──────────────────────────────────────────────────────────────────────

    async def test_openai_chat_non_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/chat/completions non-stream returns valid response with usage."""
        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]
        assert "content" in data["choices"][0]["message"]
        assert "usage" in data
        assert data["usage"]["prompt_tokens"] > 0
        assert data["usage"]["completion_tokens"] > 0

    async def test_openai_chat_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/chat/completions stream returns SSE with delta chunks."""
        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        chunks = [c for c in body.split("\n\n") if c.strip()]
        # Verify at least one data chunk with delta
        data_chunks = [c for c in chunks if c.startswith("data: ") and c != "data: [DONE]"]
        assert len(data_chunks) > 0, "Expected at least one SSE data chunk"

        # Check for delta content in at least one chunk
        import json

        has_delta = False
        has_usage = False
        for chunk in data_chunks:
            payload = chunk.removeprefix("data: ").strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                parsed = json.loads(payload)
                if parsed.get("choices") and parsed["choices"][0].get("delta"):
                    has_delta = True
                if parsed.get("usage"):
                    has_usage = True
            except json.JSONDecodeError:
                continue

        assert has_delta, "Expected at least one chunk with choices[0].delta"
        # Verify final [DONE] marker
        assert "data: [DONE]" in body, "Expected data: [DONE] at end of stream"

    # ──────────────────────────────────────────────────────────────────────
    # Anthropic Messages
    # ──────────────────────────────────────────────────────────────────────

    async def test_anthropic_messages_non_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/anthropic/messages non-stream returns content + usage."""
        resp = await app_client.post(
            "/v1/anthropic/messages",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "content" in data
        assert len(data["content"]) > 0
        assert "text" in data["content"][0]
        assert "usage" in data
        assert data["usage"]["input_tokens"] > 0

    async def test_anthropic_messages_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/anthropic/messages stream returns SSE with Anthropic events."""
        resp = await app_client.post(
            "/v1/anthropic/messages",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
                "stream": True,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        lines = body.split("\n")
        events = [l.removeprefix("event: ").strip() for l in lines if l.startswith("event: ")]
        data_lines = [l.removeprefix("data: ").strip() for l in lines if l.startswith("data: ")]

        # Verify Anthropic SSE event structure
        assert "message_start" in events, "Expected event: message_start"
        assert "content_block_delta" in events, "Expected event: content_block_delta"
        assert "message_stop" in events, "Expected event: message_stop"

        # Verify at least one delta has text
        import json

        has_text_delta = False
        for data in data_lines:
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "content_block_delta":
                    delta = parsed.get("delta", {})
                    if delta.get("text"):
                        has_text_delta = True
                        break
            except json.JSONDecodeError:
                continue
        assert has_text_delta, "Expected at least one content_block_delta with text"

    # ──────────────────────────────────────────────────────────────────────
    # OpenAI Responses
    # ──────────────────────────────────────────────────────────────────────

    async def test_openai_responses_non_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/responses non-stream returns output array."""
        resp = await app_client.post(
            "/v1/responses",
            json={
                "model": "gpt-4o-mini",
                "input": "hi",
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "output" in data
        assert len(data["output"]) > 0

    async def test_openai_responses_stream(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis
    ):
        """POST /v1/responses stream returns SSE with response.* events."""
        resp = await app_client.post(
            "/v1/responses",
            json={
                "model": "gpt-4o-mini",
                "input": "hi",
                "stream": True,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        lines = body.split("\n")
        events = [l.removeprefix("event: ").strip() for l in lines if l.startswith("event: ")]

        # Verify Responses API SSE event structure
        response_events = [e for e in events if e.startswith("response.")]
        assert len(response_events) > 0, "Expected response.* events in stream"
        assert "response.created" in events, "Expected event: response.created"
        assert "response.completed" in events, "Expected event: response.completed"

    # ──────────────────────────────────────────────────────────────────────
    # Balance & Billing
    # ──────────────────────────────────────────────────────────────────────

    async def test_balance_deducted_after_relay(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis, cache_redis
    ):
        """Balance in Redis decreases after a successful relay call (D-08)."""
        # Record balance before
        balance_before = int(await cache_redis.get(f"user:quota:{seed_user.id}"))

        # Make a non-stream chat call
        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200

        # Wait for fire-and-forget settlement
        await asyncio.sleep(0.5)

        # Read balance after
        balance_after = int(await cache_redis.get(f"user:quota:{seed_user.id}"))
        assert balance_after < balance_before, (
            f"Expected balance to decrease: before={balance_before}, after={balance_after}"
        )

    async def test_call_log_persisted(
        self, app_client, seed_user, seed_api_key, init_relay, seed_balance_in_redis, db_session
    ):
        """Call log is persisted to DB after relay completes."""
        # Make a non-stream chat call
        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200

        # Wait for fire-and-forget DB write
        await asyncio.sleep(0.5)

        # Query call log
        result = await db_session.execute(
            select(ApiCallLog).where(ApiCallLog.user_id == seed_user.id)
        )
        logs = result.scalars().all()
        assert len(logs) >= 1, "Expected at least one call log entry"
        assert logs[0].model_name == "gpt-4o-mini"

    # ──────────────────────────────────────────────────────────────────────
    # Error cases
    # ──────────────────────────────────────────────────────────────────────

    async def test_invalid_api_key_returns_401(
        self, app_client, seed_user, seed_api_key, init_relay
    ):
        """Invalid API key returns 401."""
        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers={"Authorization": "Bearer sk-invalid-key-does-not-exist"},
        )
        assert resp.status_code == 401

    async def test_insufficient_balance_returns_402(
        self, app_client, seed_user, seed_api_key, init_relay, cache_redis
    ):
        """Zero balance returns 402 insufficient balance error."""
        # Set balance to 0 in Redis
        await cache_redis.set(f"user:quota:{seed_user.id}", "0")

        resp = await app_client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers=AUTH_HEADER,
        )
        # Should return 402 or 400 with insufficient balance
        assert resp.status_code in (400, 402), (
            f"Expected 400 or 402, got {resp.status_code}: {resp.text}"
        )
