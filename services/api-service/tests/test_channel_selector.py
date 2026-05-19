"""Tests for relay/channel_selector.py — ChannelSelector weighted RR + cooldown + auto-disable."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from api_service.relay.channel_selector import ChannelRateLimited, ChannelSelector


def _make_channel(slug: str, weight: int = 1, priority: int = 10, pool_account_id: int = 1) -> dict:
    return {
        "channel_slug": slug,
        "provider_slug": "test",
        "api_key": "sk-test",
        "api_base": "https://api.example.com",
        "upstream_model": "gpt-4",
        "weight": weight,
        "priority": priority,
        "pool_account_id": pool_account_id,
    }


class TestChannelSelectorWeightedRR:
    """test_select_weighted_round_robin: 2 channels with weight 2 and 1, verify distribution."""

    def test_select_weighted_round_robin(self):
        selector = ChannelSelector()
        channels = [
            _make_channel("ch-a", weight=2),
            _make_channel("ch-b", weight=1),
        ]

        results = [selector.select("model-x", channels)["channel_slug"] for _ in range(3)]
        # Weight 2 + 1 = 3 total. Over 3 calls: ch-a gets 2, ch-b gets 1
        assert results.count("ch-a") == 2
        assert results.count("ch-b") == 1


class TestChannelSelectorFailure:
    """test_select_excludes_failed_channel: report_failure on channel A, verify next select skips A."""

    def test_select_excludes_failed_channel(self):
        selector = ChannelSelector(cooldown_seconds=60.0)
        channels = [
            _make_channel("ch-a", weight=1),
            _make_channel("ch-b", weight=1),
        ]

        selector.report_failure("ch-a")
        # All subsequent selects should pick ch-b while ch-a is in cooldown
        for _ in range(5):
            assert selector.select("model-x", channels)["channel_slug"] == "ch-b"


class TestChannelSelectorAutoDisable:
    """test_select_auto_disable_after_threshold: report_failure 5 times, verify channel disabled."""

    def test_select_auto_disable_after_threshold(self):
        selector = ChannelSelector(
            cooldown_seconds=1.0,
            auto_disable_enabled=True,
            auto_disable_threshold=5,
            auto_disable_cooldown_seconds=300.0,
        )
        channels = [
            _make_channel("ch-a", weight=1),
            _make_channel("ch-b", weight=1),
        ]

        # Report 5 failures to trigger auto-disable
        for _ in range(5):
            selector.report_failure("ch-a")

        # Even after cooldown_seconds passes, auto_disable_cooldown keeps it out
        with patch("time.monotonic", return_value=time.monotonic() + 2.0):
            # ch-a should still be disabled (auto_disable_cooldown=300s)
            assert not selector.is_channel_available("ch-a")


class TestChannelSelectorReportSuccess:
    """test_report_success_clears_failure: report_failure then report_success, verify available."""

    def test_report_success_clears_failure(self):
        selector = ChannelSelector(cooldown_seconds=60.0)
        channels = [
            _make_channel("ch-a", weight=1),
            _make_channel("ch-b", weight=1),
        ]

        selector.report_failure("ch-a")
        assert not selector.is_channel_available("ch-a")

        selector.report_success("ch-a")
        assert selector.is_channel_available("ch-a")


class TestChannelSelectorPriorityTierDescent:
    """test_select_priority_tier_descent: channels with priority 10 and 5."""

    def test_select_priority_tier_descent(self):
        selector = ChannelSelector()
        channels = [
            _make_channel("ch-high", weight=1, priority=10),
            _make_channel("ch-low", weight=1, priority=5),
        ]

        # retry_tier=0 picks highest priority (10)
        result = selector.select("model-x", channels, retry_tier=0)
        assert result["channel_slug"] == "ch-high"

        # retry_tier=1 descends to next priority (5)
        result = selector.select("model-x", channels, retry_tier=1)
        assert result["channel_slug"] == "ch-low"


class TestChannelSelectorRateLimited:
    """test_select_rate_limited_accounts_excluded."""

    def test_select_rate_limited_accounts_excluded(self):
        selector = ChannelSelector()
        channels = [
            _make_channel("ch-a", weight=1, pool_account_id=1),
            _make_channel("ch-b", weight=1, pool_account_id=2),
        ]

        result = selector.select(
            "model-x", channels, rate_limited_accounts=frozenset({1})
        )
        assert result["channel_slug"] == "ch-b"


class TestChannelSelectorHealthCache:
    """test_update_health_cache: mark channel:model as unhealthy, verify excluded."""

    def test_update_health_cache(self):
        selector = ChannelSelector()
        channels = [
            _make_channel("ch-a", weight=1),
            _make_channel("ch-b", weight=1),
        ]

        selector.update_health_cache({"ch-a:model-x": "unhealthy"})
        # ch-a should be excluded for model-x
        for _ in range(5):
            result = selector.select("model-x", channels)
            assert result["channel_slug"] == "ch-b"
