"""Tests for relay/inference_client.py — InferenceClient HTTP + circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from app.relay.inference_client import ClassifyResult, InferenceClient


@pytest_asyncio.fixture
async def client():
    """Create an InferenceClient with short timeouts for testing."""
    c = InferenceClient(
        base_url="http://inference.test",
        secret="test-secret",
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.01,
        circuit_breaker_threshold=3,
        circuit_breaker_cooldown=10.0,
    )
    yield c
    await c.close()


class TestClassifySuccess:
    """test_classify_success: mock httpx returning 200 with JSON."""

    @pytest.mark.asyncio
    async def test_classify_success(self, client: InferenceClient):
        response_data = {"selected_model": "gpt-4", "routing_tier": 1}
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = response_data

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.classify([{"role": "user", "content": "hello"}])

        assert result.success is True
        assert result.data == response_data
        assert result.http_status == 200


class TestClassifyRetryOn5xx:
    """test_classify_retry_on_5xx: mock first call 500, second call 200."""

    @pytest.mark.asyncio
    async def test_classify_retry_on_5xx(self, client: InferenceClient):
        fail_response = MagicMock(spec=httpx.Response)
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"
        fail_response.request = MagicMock()
        fail_response.json.return_value = {}

        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.json.return_value = {"selected_model": "gpt-4"}

        with patch.object(
            client._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = [fail_response, success_response]
            result = await client.classify([{"role": "user", "content": "hi"}])

        assert result.success is True
        assert result.data == {"selected_model": "gpt-4"}
        assert mock_post.call_count == 2


class TestClassifyCircuitBreakerOpens:
    """test_classify_circuit_breaker_opens: 3 consecutive failures, verify CB opens."""

    @pytest.mark.asyncio
    async def test_classify_circuit_breaker_opens(self, client: InferenceClient):
        # Simulate 3 rounds of all-attempts-failed to trip the CB
        # Each round = 2 attempts (1 + max_retries=1), both fail with ConnectError
        for _ in range(3):
            with patch.object(
                client._client, "post", new_callable=AsyncMock
            ) as mock_post:
                mock_post.side_effect = httpx.ConnectError("connection refused")
                await client.classify([{"role": "user", "content": "test"}])

        # Now the circuit breaker should be open — next call returns without HTTP
        with patch.object(
            client._client, "post", new_callable=AsyncMock
        ) as mock_post:
            result = await client.classify([{"role": "user", "content": "test"}])
            mock_post.assert_not_called()

        assert result.success is False
        assert result.error_code == "circuit_open"


class TestClassifyCircuitBreakerResets:
    """test_classify_circuit_breaker_resets_after_cooldown."""

    @pytest.mark.asyncio
    async def test_classify_circuit_breaker_resets_after_cooldown(self, client: InferenceClient):
        # Trip the circuit breaker
        for _ in range(3):
            with patch.object(
                client._client, "post", new_callable=AsyncMock
            ) as mock_post:
                mock_post.side_effect = httpx.ConnectError("connection refused")
                await client.classify([{"role": "user", "content": "test"}])

        # Advance time past cooldown (10s)
        future_time = time.monotonic() + 11.0
        with patch("time.monotonic", return_value=future_time):
            success_response = MagicMock(spec=httpx.Response)
            success_response.status_code = 200
            success_response.json.return_value = {"selected_model": "gpt-4"}

            with patch.object(
                client._client, "post", new_callable=AsyncMock
            ) as mock_post:
                mock_post.return_value = success_response
                result = await client.classify([{"role": "user", "content": "test"}])

        assert result.success is True


class TestClassifyConnectionError:
    """test_classify_connection_error: mock httpx.ConnectError."""

    @pytest.mark.asyncio
    async def test_classify_connection_error(self, client: InferenceClient):
        with patch.object(
            client._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            result = await client.classify([{"role": "user", "content": "test"}])

        assert result.success is False
        assert result.error_code == "unavailable"
