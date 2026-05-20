"""Relay singleton dependency management — module-level getters + init_relay_globals.

All relay singletons are initialized in lifespan and accessed via get_* functions.
Raises RuntimeError if accessed before initialization.
"""

from __future__ import annotations

import logging

from app.relay.channel_affinity import ChannelAffinityStore
from app.relay.channel_selector import ChannelSelector
from app.relay.config_cache import RoutingConfigCache
from app.relay.inference_client import InferenceClient
from app.relay.rate_limiter import RateLimiter
from app.relay.sdk_clients import SdkClientPool

logger = logging.getLogger(__name__)

# ── Module-level singletons (initially None) ─────────────────────────────────
_routing_config_cache: RoutingConfigCache | None = None
_inference_client: InferenceClient | None = None
_channel_selector: ChannelSelector | None = None
_affinity_store: ChannelAffinityStore | None = None
_sdk_client_pool: SdkClientPool | None = None
_rate_limiter: RateLimiter | None = None


def init_relay_globals(
    *,
    config_cache: RoutingConfigCache,
    inference_client: InferenceClient,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None = None,
    sdk_client_pool: SdkClientPool | None = None,
    rate_limiter: RateLimiter | None = None,
) -> None:
    """Initialize all relay singletons. Called during lifespan startup."""
    global _routing_config_cache, _inference_client, _channel_selector
    global _affinity_store, _sdk_client_pool, _rate_limiter
    _routing_config_cache = config_cache
    _inference_client = inference_client
    _channel_selector = channel_selector
    _affinity_store = affinity_store
    _sdk_client_pool = sdk_client_pool
    _rate_limiter = rate_limiter
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


def get_sdk_client_pool() -> SdkClientPool:
    """Return the SdkClientPool singleton."""
    if _sdk_client_pool is None:
        raise RuntimeError("SdkClientPool not initialized — call init_relay_globals first")
    return _sdk_client_pool


def get_rate_limiter() -> RateLimiter:
    """Return the RateLimiter singleton."""
    if _rate_limiter is None:
        raise RuntimeError("RateLimiter not initialized — call init_relay_globals first")
    return _rate_limiter


async def shutdown_relay() -> None:
    """Shut down relay resources (InferenceClient httpx pool + SdkClientPool)."""
    global _inference_client, _sdk_client_pool
    if _inference_client is not None:
        await _inference_client.close()
        _inference_client = None
        logger.info("relay InferenceClient closed")
    if _sdk_client_pool is not None:
        await _sdk_client_pool.close_all()
        _sdk_client_pool = None
        logger.info("relay SdkClientPool closed")


__all__ = [
    "get_affinity_store",
    "get_channel_selector",
    "get_inference_client",
    "get_rate_limiter",
    "get_routing_config_cache",
    "get_sdk_client_pool",
    "init_relay_globals",
    "shutdown_relay",
]
