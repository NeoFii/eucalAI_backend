"""Tests for SdkClientPool LRU behavior."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from api_service.relay.sdk_clients import SdkClientPool


class TestSdkClientPool:
    def test_get_openai_returns_same_instance(self):
        """Same (base_url, api_key) should return the same client instance."""
        pool = SdkClientPool(max_size=10)
        client1 = pool.get_openai("http://api.example.com", "sk-test")
        client2 = pool.get_openai("http://api.example.com", "sk-test")
        assert client1 is client2

    def test_get_anthropic_returns_same_instance(self):
        """Same (base_url, api_key) should return the same Anthropic client."""
        pool = SdkClientPool(max_size=10)
        client1 = pool.get_anthropic("http://api.example.com", "sk-ant-test")
        client2 = pool.get_anthropic("http://api.example.com", "sk-ant-test")
        assert client1 is client2

    def test_different_keys_return_different_instances(self):
        """Different api_keys should return different client instances."""
        pool = SdkClientPool(max_size=10)
        client1 = pool.get_openai("http://api.example.com", "sk-key1")
        client2 = pool.get_openai("http://api.example.com", "sk-key2")
        assert client1 is not client2

    def test_lru_eviction(self):
        """When pool exceeds max_size, oldest client should be evicted."""
        pool = SdkClientPool(max_size=2)

        # Add 3 clients — first one should be evicted
        client1 = pool.get_openai("http://a.com", "key1")
        client2 = pool.get_openai("http://b.com", "key2")
        client3 = pool.get_openai("http://c.com", "key3")

        # client1 should have been evicted (oldest, not accessed)
        client1_again = pool.get_openai("http://a.com", "key1")
        assert client1_again is not client1  # new instance created

        # client2 and client3 should still be there (or client3 at least)
        # After adding client1_again, client2 is now oldest
        assert len(pool._openai_clients) == 2

    def test_lru_access_refreshes_position(self):
        """Accessing a client moves it to end, preventing eviction."""
        pool = SdkClientPool(max_size=2)

        client1 = pool.get_openai("http://a.com", "key1")
        client2 = pool.get_openai("http://b.com", "key2")

        # Access client1 again — moves it to end
        pool.get_openai("http://a.com", "key1")

        # Add client3 — should evict client2 (now oldest)
        pool.get_openai("http://c.com", "key3")

        # client1 should still be there
        assert pool.get_openai("http://a.com", "key1") is client1

    @pytest.mark.asyncio
    async def test_close_all_clears_pool(self):
        """close_all should clear all clients from the pool."""
        pool = SdkClientPool(max_size=10)
        pool.get_openai("http://a.com", "key1")
        pool.get_anthropic("http://b.com", "key2")

        assert len(pool._openai_clients) == 1
        assert len(pool._anthropic_clients) == 1

        await pool.close_all()

        assert len(pool._openai_clients) == 0
        assert len(pool._anthropic_clients) == 0
