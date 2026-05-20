"""Channel selector: weighted round-robin with failure cooldown, auto-disable, and priority-tier descent.

Ported from router-service/src/services/channel_selector.py.
Decisions: D-18 (full port), D-20 (per-worker independent state).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.common.core.exceptions import APIException

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_SECONDS = 30.0


class ChannelRateLimited(APIException):
    """All channels for a model are rate-limited."""

    def __init__(self, detail: str = "All upstream channels are rate-limited"):
        super().__init__(status_code=429, detail=detail, code="channel_rate_limited")


class ChannelSelector:
    """Select a channel using weighted round-robin with priority-tier descent and auto-disable."""

    def __init__(
        self,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
        auto_disable_enabled: bool = True,
        auto_disable_threshold: int = 5,
        auto_disable_cooldown_seconds: float = 300.0,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._auto_disable_enabled = auto_disable_enabled
        self._auto_disable_threshold = auto_disable_threshold
        self._auto_disable_cooldown = auto_disable_cooldown_seconds

        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._failures: dict[str, float] = {}
        self._failure_counts: dict[str, int] = {}
        self._disabled_until: dict[str, float] = {}
        self._health_cache: dict[str, str] = {}

    def select(
        self,
        model_slug: str,
        channels: list[dict[str, Any]],
        *,
        excluded_slugs: frozenset[str] | None = None,
        retry_tier: int = 0,
        rate_limited_accounts: frozenset[int] | None = None,
    ) -> dict[str, Any]:
        """Select a channel via weighted round-robin with priority-tier descent."""
        if not channels:
            raise KeyError(f"no channels available for model: {model_slug}")

        now = time.monotonic()
        excluded = excluded_slugs or frozenset()
        rl_accounts = rate_limited_accounts or frozenset()

        with self._lock:
            available = [
                ch for ch in channels
                if ch["channel_slug"] not in excluded
                and self._disabled_until.get(ch["channel_slug"], 0) < now
                and self._failures.get(ch["channel_slug"], 0) < now
                and self._health_cache.get(
                    f"{ch['channel_slug']}:{model_slug}"
                ) != "unhealthy"
                and ch.get("pool_account_id") not in rl_accounts
            ]

        if not available:
            non_rl = [
                ch for ch in channels
                if ch["channel_slug"] not in excluded
                and ch.get("pool_account_id") not in rl_accounts
            ]
            if non_rl:
                available = non_rl
            else:
                non_excluded = [ch for ch in channels if ch["channel_slug"] not in excluded]
                if non_excluded and rl_accounts:
                    raise ChannelRateLimited(
                        f"all channels for model {model_slug} are rate-limited"
                    )
                available = non_excluded if non_excluded else channels

        available.sort(key=lambda c: (-c.get("priority", 0), c.get("channel_slug", "")))

        unique_priorities = sorted({c.get("priority", 0) for c in available}, reverse=True)
        if unique_priorities:
            tier_idx = min(retry_tier, len(unique_priorities) - 1)
            target_priority = unique_priorities[tier_idx]
            tier_channels = [c for c in available if c.get("priority", 0) == target_priority]
            if tier_channels:
                available = tier_channels

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
        """Record a failure for a channel, applying cooldown and auto-disable."""
        should_disable = False
        count = 0
        with self._lock:
            self._failures[channel_slug] = time.monotonic() + self._cooldown
            count = self._failure_counts.get(channel_slug, 0) + 1
            self._failure_counts[channel_slug] = count
            if self._auto_disable_enabled and count >= self._auto_disable_threshold:
                self._disabled_until[channel_slug] = time.monotonic() + self._auto_disable_cooldown
                should_disable = True

        if should_disable:
            logger.warning(
                "channel %s auto-disabled after %d consecutive failures, cooldown %.0fs",
                channel_slug, count, self._auto_disable_cooldown,
            )
        else:
            logger.warning(
                "channel %s failed (%d/%d), cooldown %.0fs",
                channel_slug, count, self._auto_disable_threshold, self._cooldown,
            )

    def report_success(self, channel_slug: str) -> None:
        """Clear failure state for a channel."""
        with self._lock:
            self._failures.pop(channel_slug, None)
            self._failure_counts.pop(channel_slug, None)
            self._disabled_until.pop(channel_slug, None)

    def update_health_cache(self, health_data: dict[str, str]) -> None:
        """Replace the health cache atomically."""
        self._health_cache = health_data

    def is_channel_available(self, channel_slug: str) -> bool:
        """Check if a channel is not in cooldown or auto-disabled."""
        now = time.monotonic()
        with self._lock:
            return (
                self._disabled_until.get(channel_slug, 0) < now
                and self._failures.get(channel_slug, 0) < now
            )


__all__ = ["ChannelRateLimited", "ChannelSelector"]
