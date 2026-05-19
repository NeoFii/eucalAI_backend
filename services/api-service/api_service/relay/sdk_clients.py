"""SDK client pool: reusable AsyncOpenAI and AsyncAnthropic instances."""

from __future__ import annotations

import threading
from collections import OrderedDict

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI


class SdkClientPool:
    """LRU-bounded pool of SDK client instances keyed by (base_url, api_key)."""

    def __init__(self, max_size: int = 64) -> None:
        self._max_size = max_size
        self._openai_clients: OrderedDict[tuple[str, str], AsyncOpenAI] = OrderedDict()
        self._anthropic_clients: OrderedDict[tuple[str, str], AsyncAnthropic] = OrderedDict()
        self._lock = threading.Lock()

    def get_openai(self, base_url: str, api_key: str) -> AsyncOpenAI:
        key = (base_url, api_key)
        with self._lock:
            if key in self._openai_clients:
                self._openai_clients.move_to_end(key)
                return self._openai_clients[key]
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            self._openai_clients[key] = client
            if len(self._openai_clients) > self._max_size:
                self._openai_clients.popitem(last=False)
            return client

    def get_anthropic(self, base_url: str, api_key: str) -> AsyncAnthropic:
        key = (base_url, api_key)
        with self._lock:
            if key in self._anthropic_clients:
                self._anthropic_clients.move_to_end(key)
                return self._anthropic_clients[key]
            client = AsyncAnthropic(base_url=base_url, api_key=api_key)
            self._anthropic_clients[key] = client
            if len(self._anthropic_clients) > self._max_size:
                self._anthropic_clients.popitem(last=False)
            return client

    async def close_all(self) -> None:
        with self._lock:
            for client in self._openai_clients.values():
                await client.close()
            self._openai_clients.clear()
            for client in self._anthropic_clients.values():
                await client.close()
            self._anthropic_clients.clear()
