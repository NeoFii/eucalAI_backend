"""Routing orchestration: classify via inference-service, resolve upstream target."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from router_service.dependencies import get_inference_client, get_runtime_store
from router_service.logging import log_routing_decision
from router_service.services.upstream import resolve_model_provider_target

_SENSITIVE_RE = re.compile(
    r"((?:key|token|secret|password|auth)[=:]\S{0,60}|https?://\S+)",
    re.IGNORECASE,
)


def sanitize_error(exc: Exception, max_len: int = 200) -> str:
    raw = str(exc)[:max_len]
    return _SENSITIVE_RE.sub("[REDACTED]", raw)


async def route_and_resolve(
    *,
    requested_model: str,
    messages: list[dict[str, Any]],
    request_id: str,
    input_preview: str = "",
    messages_count: int = 0,
    is_stream: bool = False,
) -> tuple[str, dict[str, str], dict[str, Any] | None]:
    config = get_runtime_store().load()

    route_result = None
    selected_model = requested_model

    if requested_model == config["router_alias"]:
        inference_client = get_inference_client()
        route_result = await inference_client.classify(
            messages, request_id=request_id,
        )
        selected_model = route_result["selected_model"]

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
        )
    elif requested_model not in config["model_providers"]:
        raise HTTPException(status_code=404, detail=f"unsupported model: {requested_model}")

    target_info = resolve_model_provider_target(selected_model, config["model_providers"])
    return selected_model, target_info, route_result
