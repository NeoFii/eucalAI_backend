"""Routing orchestration: classify via inference-service, resolve upstream target.

Ported from router-service/src/services/routing.py.
Decision D-18: Full port of route_and_resolve() with explicit dependency parameters.
Threat T-06-13: Only models in user_facing_aliases accepted.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from api_service.relay.channel_affinity import ChannelAffinityStore
from api_service.relay.channel_selector import ChannelSelector
from api_service.relay.config_cache import RoutingConfigCache
from api_service.relay.inference_client import InferenceClient
from api_service.relay.upstream import (
    normalize_api_base,
    resolve_model_channel_target,
    resolve_model_provider_target,
    _validate_upstream_url,
)

logger = logging.getLogger(__name__)

_FALLBACK_ERROR_CODES = {"config", "unavailable", "model_runtime", "circuit_open", "timeout"}
_DIRECT_ERROR_CODES = {"auth": 502, "validation": 400}


class RoutingError(HTTPException):
    """Routing-specific HTTP error with error_code."""

    def __init__(self, status_code: int, error_code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


async def route_and_resolve(
    *,
    requested_model: str,
    messages: list[dict[str, Any]],
    request_id: str,
    config_cache: RoutingConfigCache,
    inference_client: InferenceClient,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None = None,
    affinity_key: str | None = None,
    input_preview: str = "",
    messages_count: int = 0,
    is_stream: bool = False,
) -> tuple[str, dict[str, str], dict[str, Any] | None, dict[str, Any]]:
    """Validate requested_model, route via inference-service, resolve upstream.

    Only values present in config["user_facing_aliases"] are accepted.
    Unknown models are rejected with HTTP 400 / error_code=invalid_model (T-06-13).

    Returns: (selected_model, target_info, route_result, route_meta)
    """
    config = config_cache.load()

    route_meta: dict[str, Any] = {
        "error_code": None,
    }

    route_result = None
    selected_model = requested_model

    user_facing_aliases = config.get("user_facing_aliases") or [config["router_alias"]]

    if requested_model not in user_facing_aliases:
        allowed = ", ".join(user_facing_aliases)
        raise RoutingError(
            status_code=400,
            error_code="invalid_model",
            detail=f"Model '{requested_model}' is not allowed, use one of: {allowed}",
        )

    if requested_model == config["router_alias"]:
        classify_result = await inference_client.classify(
            messages, request_id=request_id,
        )

        if classify_result.success:
            route_result = classify_result.data
            selected_model = route_result["selected_model"]
            route_meta["inference_config_version"] = route_result.get("config_version")
            route_meta["inference_config_source"] = route_result.get("config_source")
        else:
            error_code = classify_result.error_code or "unavailable"
            route_meta["error_code"] = error_code

            if error_code in _DIRECT_ERROR_CODES:
                raise RoutingError(
                    status_code=_DIRECT_ERROR_CODES[error_code],
                    error_code=f"inference_{error_code}",
                    detail=classify_result.error_message or "Inference service unavailable",
                )

            tier3_model = config["tier_model_map"].get(3)
            if tier3_model and tier3_model in _available_models(config):
                selected_model = tier3_model
                logger.warning(
                    "inference classify failed (error_code=%s), falling back to tier 3: %s",
                    error_code, tier3_model,
                )
            else:
                raise RoutingError(
                    status_code=503,
                    error_code="no_fallback",
                    detail="Inference service unavailable, no fallback model",
                )
    else:
        # Non-alias entry in user_facing_aliases — resolve directly if available
        if requested_model in _available_models(config):
            selected_model = requested_model
        else:
            classify_result = await inference_client.classify(
                messages, request_id=request_id,
            )
            if classify_result.success:
                route_result = classify_result.data
                selected_model = route_result["selected_model"]
            else:
                tier3_model = config["tier_model_map"].get(3)
                if tier3_model and tier3_model in _available_models(config):
                    selected_model = tier3_model
                else:
                    raise RoutingError(
                        status_code=503,
                        error_code="no_fallback",
                        detail="Cannot resolve model alias, no fallback available",
                    )

    # Validate pricing exists
    model_prices = config.get("model_prices", {})
    if selected_model not in model_prices:
        logger.error(
            "model %r has no user-facing prices in model_prices config — "
            "check model_catalog.routing_slug; request rejected",
            selected_model,
        )
        raise RoutingError(
            status_code=428,
            error_code="pricing_not_configured",
            detail="Model temporarily unavailable",
        )

    target_info = await _resolve_target_with_affinity(
        selected_model, config, channel_selector, affinity_store, affinity_key
    )
    return selected_model, target_info, route_result, route_meta


def _available_models(config: dict) -> set:
    """Return set of models that have channels or providers configured."""
    if "model_channels" in config:
        return set(config["model_channels"].keys())
    return set(config.get("model_providers", {}).keys())


async def _resolve_target(
    model: str,
    config: dict,
    channel_selector: ChannelSelector,
    *,
    excluded_slugs: frozenset[str] | None = None,
    retry_tier: int = 0,
) -> dict:
    """Resolve model to upstream target via channels or providers."""
    if "model_channels" in config and config["model_channels"]:
        rate_limited_accounts = _get_rate_limited_accounts(model, config)
        return resolve_model_channel_target(
            model, config["model_channels"], channel_selector,
            excluded_slugs=excluded_slugs, retry_tier=retry_tier,
            rate_limited_accounts=rate_limited_accounts,
        )
    return resolve_model_provider_target(model, config.get("model_providers", {}))


async def _resolve_target_with_affinity(
    model: str,
    config: dict,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None,
    affinity_key: str | None,
) -> dict:
    """Resolve target with affinity cache lookup/store."""
    if affinity_key and affinity_store is not None and "model_channels" in config:
        cached_slug = await affinity_store.get(affinity_key)
        if cached_slug:
            channels = config.get("model_channels", {}).get(model, [])
            for ch in channels:
                if ch["channel_slug"] == cached_slug:
                    if channel_selector.is_channel_available(cached_slug):
                        api_base = normalize_api_base(str(ch["api_base"]))
                        _validate_upstream_url(api_base)
                        return {
                            "logical_model": model,
                            "channel_slug": cached_slug,
                            "provider_slug": ch["provider_slug"],
                            "api_key": str(ch["api_key"]).strip(),
                            "api_base": api_base,
                            "upstream_model": str(ch["upstream_model"]).strip(),
                            "input_price_per_million": ch.get("cost_input_per_million", 0),
                            "output_price_per_million": ch.get("cost_output_per_million", 0),
                            "cached_input_price_per_million": ch.get("cost_cached_input_per_million", 0),
                            "pool_account_id": ch.get("pool_account_id"),
                            "rpm_limit": ch.get("rpm_limit"),
                        }
                    break

    target_info = await _resolve_target(model, config, channel_selector)

    if affinity_key and affinity_store is not None:
        channel_slug = target_info.get("channel_slug")
        if channel_slug:
            await affinity_store.set(affinity_key, channel_slug)

    return target_info


def _get_rate_limited_accounts(model: str, config: dict) -> frozenset[int]:
    """Check per-account RPM limits (D-23: channel-level only in Phase 6)."""
    # Phase 6 does not have a full rate limiter — returns empty set.
    # Phase 7 will implement per-account RPM checking via Redis.
    return frozenset()


__all__ = ["RoutingError", "route_and_resolve"]
