"""Routing orchestration: classify via inference-service, resolve upstream target."""

from __future__ import annotations

import logging
from typing import Any

from core.dependencies import get_config_manager, get_inference_client, get_channel_selector, get_rate_limiter, get_affinity_store
from core.exceptions import RoutingError
from utils.logging_config import log_routing_decision
from services.upstream import resolve_model_provider_target, resolve_model_channel_target, normalize_api_base

logger = logging.getLogger("router_service")

_FALLBACK_ERROR_CODES = {"config", "unavailable", "model_runtime", "circuit_open", "timeout"}
_DIRECT_ERROR_CODES = {"auth": 502, "validation": 400}


async def route_and_resolve(
    *,
    requested_model: str,
    messages: list[dict[str, Any]],
    request_id: str,
    input_preview: str = "",
    messages_count: int = 0,
    is_stream: bool = False,
    affinity_key: str | None = None,
) -> tuple[str, dict[str, str], dict[str, Any] | None, dict[str, Any]]:
    config_manager = get_config_manager()
    config = config_manager.load()

    route_meta: dict[str, Any] = {
        "config_version": config_manager.config_version,
        "config_source": config_manager.config_source,
        "error_code": None,
    }

    route_result = None
    selected_model = requested_model

    if requested_model == config["router_alias"]:
        inference_client = get_inference_client()
        classify_result = await inference_client.classify(
            messages, request_id=request_id,
        )

        if classify_result.success:
            route_result = classify_result.data
            selected_model = route_result["selected_model"]
            inference_cv = route_result.get("config_version")
            inference_cs = route_result.get("config_source")
            route_meta["inference_config_version"] = inference_cv
            route_meta["inference_config_source"] = inference_cs

            log_routing_decision(
                request_id=request_id,
                requested_model=requested_model,
                scores_0_2=route_result.get("scores_0_2"),
                proto_weighted_0_2=route_result.get("proto_weighted_0_2"),
                total_score_0_10=route_result.get("total_score_0_10"),
                score_source=route_result.get("score_source"),
                routing_tier=route_result.get("routing_tier"),
                selected_model=selected_model,
                input_preview=input_preview,
                messages_count=messages_count,
                is_stream=is_stream,
                fallback_routes=route_result.get("fallback_routes", []),
                config_version=route_meta["config_version"],
                config_source=route_meta["config_source"],
                inference_config_version=inference_cv,
                inference_config_source=inference_cs,
            )
        else:
            error_code = classify_result.error_code or "unavailable"
            route_meta["error_code"] = error_code

            if error_code in _DIRECT_ERROR_CODES:
                raise RoutingError(
                    status_code=_DIRECT_ERROR_CODES[error_code],
                    error_code=f"inference_{error_code}",
                    detail=classify_result.error_message or f"inference error: {error_code}",
                )

            tier3_model = config["tier_model_map"].get(3)
            if tier3_model and tier3_model in _available_models(config):
                selected_model = tier3_model
                logger.warning(
                    "inference classify failed (error_code=%s), falling back to tier 3: %s",
                    error_code, tier3_model,
                )
                log_routing_decision(
                    request_id=request_id,
                    requested_model=requested_model,
                    selected_model=selected_model,
                    score_source="fallback_default",
                    input_preview=input_preview,
                    messages_count=messages_count,
                    is_stream=is_stream,
                    config_version=route_meta["config_version"],
                    config_source=route_meta["config_source"],
                    error_code=error_code,
                )
            else:
                raise RoutingError(
                    status_code=503,
                    error_code="no_fallback",
                    detail="inference service unavailable and no fallback model available",
                )

    elif requested_model not in _available_models(config):
        raise RoutingError(
            status_code=404,
            error_code="model_not_found",
            detail=f"unsupported model: {requested_model}",
        )

    target_info = await _resolve_target_with_affinity(selected_model, config, affinity_key)
    return selected_model, target_info, route_result, route_meta


def _available_models(config: dict) -> set:
    if "model_channels" in config:
        return set(config["model_channels"].keys())
    return set(config.get("model_providers", {}).keys())


async def _resolve_target(
    model: str,
    config: dict,
    *,
    excluded_slugs: frozenset[str] | None = None,
    retry_tier: int = 0,
) -> dict:
    if "model_channels" in config and config["model_channels"]:
        selector = get_channel_selector()
        rate_limited_accounts = await _get_rate_limited_accounts(model, config)
        return resolve_model_channel_target(
            model, config["model_channels"], selector,
            excluded_slugs=excluded_slugs, retry_tier=retry_tier,
            rate_limited_accounts=rate_limited_accounts,
        )
    return resolve_model_provider_target(model, config.get("model_providers", {}))


async def _resolve_target_with_affinity(
    model: str,
    config: dict,
    affinity_key: str | None,
) -> dict:
    affinity_store = get_affinity_store()

    if affinity_key and affinity_store is not None and "model_channels" in config:
        cached_slug = await affinity_store.get(affinity_key)
        if cached_slug:
            channels = config.get("model_channels", {}).get(model, [])
            for ch in channels:
                if ch["channel_slug"] == cached_slug:
                    selector = get_channel_selector()
                    import time
                    now = time.monotonic()
                    slug = ch["channel_slug"]
                    with selector._lock:
                        is_available = (
                            selector._disabled_until.get(slug, 0) < now
                            and selector._failures.get(slug, 0) < now
                        )
                    if is_available:
                        from services.upstream import _validate_upstream_url
                        api_base = normalize_api_base(str(ch["api_base"]))
                        _validate_upstream_url(api_base)
                        logger.debug("affinity hit: %s -> %s", affinity_key, cached_slug)
                        return {
                            "logical_model": model,
                            "channel_slug": slug,
                            "provider_slug": ch["provider_slug"],
                            "api_key": str(ch["api_key"]).strip(),
                            "api_base": api_base,
                            "upstream_model": str(ch["upstream_model"]).strip(),
                            "input_price_per_million": ch.get("input_price_per_million", 0),
                            "output_price_per_million": ch.get("output_price_per_million", 0),
                            "cached_input_price_per_million": ch.get("cached_input_price_per_million", 0),
                            "pool_account_id": ch.get("pool_account_id"),
                            "rpm_limit": ch.get("rpm_limit"),
                        }
                    break

    target_info = await _resolve_target(model, config)

    if affinity_key and affinity_store is not None:
        channel_slug = target_info.get("channel_slug")
        if channel_slug:
            await affinity_store.set(affinity_key, channel_slug)

    return target_info


async def _get_rate_limited_accounts(model: str, config: dict) -> frozenset[int]:
    limiter = get_rate_limiter()
    if limiter is None:
        return frozenset()
    channels = config.get("model_channels", {}).get(model, [])
    limited: set[int] = set()
    for ch in channels:
        account_id = ch.get("pool_account_id")
        rpm_limit = ch.get("rpm_limit")
        if account_id is not None and rpm_limit is not None:
            if not await limiter.is_account_available(account_id, rpm_limit):
                limited.add(account_id)
    return frozenset(limited)
