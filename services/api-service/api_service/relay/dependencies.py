"""Relay singleton dependency management — module-level getters + init_relay_globals.

All relay singletons are initialized in lifespan and accessed via get_* functions.
Raises RuntimeError if accessed before initialization.
"""

from __future__ import annotations

import logging

from api_service.relay.channel_affinity import ChannelAffinityStore
from api_service.relay.channel_selector import ChannelSelector
from api_service.relay.config_cache import RoutingConfigCache
from api_service.relay.inference_client import InferenceClient

logger = logging.getLogger(__name__)

# ── Module-level singletons (initially None) ─────────────────────────────────
_routing_config_cache: RoutingConfigCache | None = None
_inference_client: InferenceClient | None = None
_channel_selector: ChannelSelector | None = None
_affinity_store: ChannelAffinityStore | None = None


def init_relay_globals(
    *,
    config_cache: RoutingConfigCache,
    inference_client: InferenceClient,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None = None,
) -> None:
    """Initialize all relay singletons. Called during lifespan startup."""
    global _routing_config_cache, _inference_client, _channel_selector, _affinity_store
    _routing_config_cache = config_cache
    _inference_client = inference_client
    _channel_selector = channel_selector
    _affinity_store = affinity_store
    logger.info("relay globals initialized")


def get_routing_config_cache() -> RoutingConfigCache:
    """Return the RoutingConfigCache singleton."""
    if _routing_config_cache is None:
        raise RuntimeError("RoutingConfigCache not initialized — call init_relay_globals first")
    return _routing_config_cache


def get_inference_client() -> InferenceClient:
    """Return the InferenceClient singleton."""
    if _inference_client is None:
        raise RuntimeError("InferenceClient not initialized — call init_relay_globals first")
    return _inference_client


def get_channel_selector() -> ChannelSelector:
    """Return the ChannelSelector singleton."""
    if _channel_selector is None:
        raise RuntimeError("ChannelSelector not initialized — call init_relay_globals first")
    return _channel_selector


def get_affinity_store() -> ChannelAffinityStore | None:
    """Return the ChannelAffinityStore singleton (may be None if disabled)."""
    return _affinity_store


async def shutdown_relay() -> None:
    """Shut down relay resources (InferenceClient httpx pool)."""
    global _inference_client
    if _inference_client is not None:
        await _inference_client.close()
        _inference_client = None
        logger.info("relay InferenceClient closed")


__all__ = [
    "get_affinity_store",
    "get_channel_selector",
    "get_inference_client",
    "get_routing_config_cache",
    "init_relay_globals",
    "shutdown_relay",
]
