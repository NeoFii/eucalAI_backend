"""Channel selector: weighted round-robin with failure cooldown."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

_logger = logging.getLogger("router_service")

_DEFAULT_COOLDOWN_SECONDS = 30.0


class ChannelSelector:
    """Select a channel from the pool using weighted round-robin with failure tracking."""

    def __init__(self, cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS) -> None:
        self._cooldown = cooldown_seconds
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._failures: dict[str, float] = {}

    def select(self, model_slug: str, channels: list[dict[str, Any]]) -> dict[str, Any]:
        if not channels:
            raise KeyError(f"no channels available for model: {model_slug}")

        now = time.monotonic()
        with self._lock:
            available = [
                ch for ch in channels
                if self._failures.get(ch["channel_slug"], 0) < now
            ]

        if not available:
            available = channels

        available.sort(key=lambda c: (-c.get("priority", 0), c.get("channel_slug", "")))

        total_weight = sum(max(c.get("weight", 1), 1) for c in available)
        with self._lock:
            counter = self._counters.get(model_slug, 0)
            idx = counter % total_weight
            self._counters[model_slug] = counter + 1

        cumulative = 0
        for ch in available:
            cumulative += max(ch.get("weight", 1), 1)
            if idx < cumulative:
                return ch

        return available[-1]

    def report_failure(self, channel_slug: str) -> None:
        with self._lock:
            self._failures[channel_slug] = time.monotonic() + self._cooldown
        _logger.warning("channel %s marked as failed, cooldown %.0fs", channel_slug, self._cooldown)

    def report_success(self, channel_slug: str) -> None:
        with self._lock:
            self._failures.pop(channel_slug, None)
