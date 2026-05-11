"""POST /v1/completions — async legacy completions endpoint."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from common.observability import get_request_id, log_event
from core.dependencies import extract_client_ip, get_calllog_gateway, get_config_manager, get_settings, require_api_key, require_rate_limit
from gateways.user_identity import ValidatedApiKey
from utils.logging_config import build_db_request_preview, get_app_logger, log_upstream_call
from schemas.requests import CompletionRequest
from services.channel_selector import ChannelRateLimited
from core.exceptions import RoutingError, sanitize_error
from services.routing import route_and_resolve
from utils.billing import compute_cost, extract_cached_tokens
from utils.text import compute_input_hash

router = APIRouter()
logger = get_app_logger()


def _extract_messages_from_prompt(prompt: str | List[str]) -> List[Dict[str, Any]]:
    if isinstance(prompt, list):
        content = "\n".join(str(item) for item in prompt)
    else:
        content = str(prompt)
    return [{"role": "user", "content": content}]


def _completion_from_chat_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    choices = payload.get("choices") or []
    converted = []
    for index, choice in enumerate(choices):
        message = choice.get("message") if isinstance(choice, dict) else None
        converted.append({
            "text": message.get("content", "") if isinstance(message, dict) else "",
            "index": choice.get("index", index) if isinstance(choice, dict) else index,
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "logprobs": None,
        })
    return {
        "id": payload.get("id"),
        "object": "text_completion",
        "created": payload.get("created"),
        "model": payload.get("model"),
        "choices": converted,
        "usage": payload.get("usage"),
    }


@router.post("/v1/completions")
async def completions(
    request: CompletionRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="stream not supported for /v1/completions")

    requested_model = str(request.model).strip()
    messages = _extract_messages_from_prompt(request.prompt)
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"completion-{uuid.uuid4().hex[:12]}"
    input_preview = str(request.prompt)[:300]
    messages_count = len(messages)
    input_hash = compute_input_hash(messages)
    settings = get_settings()
    calllog = get_calllog_gateway()

    t_start = time.monotonic()
    create_result = await calllog.create_call_log(
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=False,
        ip=extract_client_ip(raw_request),
        input_hash=input_hash,
        status=0,
    )
    call_log_created = create_result is not None

    affinity_key = raw_request.headers.get("x-conversation-id") or getattr(request, "user", None)
    try:
        selected_model, target_info, route_result, route_meta = await route_and_resolve(
            requested_model=requested_model,
            messages=messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=len(messages),
            affinity_key=affinity_key or None,
        )
    except RoutingError as exc:
        if call_log_created:
            await calllog.update_call_log( request_id=request_id, status=2,
                error_code=exc.error_code, error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        log_event(
            logger, logging.WARNING, "chatFailed",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            isStream=False,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="classify",
            errorCode=exc.error_code,
            errorDetail=str(exc.detail)[:256],
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        raise
    except ChannelRateLimited:
        if call_log_created:
            await calllog.update_call_log( request_id=request_id, status=2,
                error_code="channel_rate_limited",
                error_msg="all channels for this model are rate-limited",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        log_event(
            logger, logging.WARNING, "chatFailed",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            isStream=False,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="rate_limit",
            errorCode="channel_rate_limited",
            errorDetail="all channels for this model are rate-limited",
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        raise HTTPException(status_code=429, detail={"error": {
            "message": "All upstream channels for this model are currently rate-limited.",
            "type": "rate_limit_error", "code": "channel_rate_limited",
        }}, headers={"Retry-After": "5"})

    config_version = route_meta.get("config_version")
    config_source = route_meta.get("config_source", "")

    routing_detail: dict | None = None
    total_score_0_10: float | None = None
    if route_result:
        routing_detail = {
            "scores_0_2": route_result.get("scores_0_2"),
            "proto_weighted_0_2": route_result.get("proto_weighted_0_2"),
            "fallback_routes": route_result.get("fallback_routes", []),
            "tier_model_map": route_result.get("tier_model_map"),
            "score_bands_raw": route_result.get("score_bands_raw"),
        }
        ts = route_result.get("total_score_0_10")
        total_score_0_10 = float(ts) if ts is not None else None

    if call_log_created:
        await calllog.update_call_log( request_id=request_id,
            selected_model=selected_model, provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            config_version=config_version, config_source=config_source,
            inference_config_version=route_meta.get("inference_config_version"),
            inference_config_source=route_meta.get("inference_config_source"),
            routing_tier=(route_result or {}).get("routing_tier"),
            score_source=(route_result or {}).get("score_source"),
            total_score_0_10=total_score_0_10,
            router_trace_id=router_trace_id,
            inference_error_code=route_meta.get("error_code"),
            messages_count=messages_count,
            routing_detail=routing_detail,
        )

    forward_payload = request.model_dump(
        mode="python",
        exclude={"model", "prompt", "stream", "stream_options", "suffix"},
        exclude_none=True,
    )

    from services.upstream_caller import UpstreamCallFailed, upstream_call_with_retry

    max_channel_retries = settings.CHANNEL_MAX_RETRIES if target_info.get("channel_slug") else 0
    try:
        litellm_response, target_info, upstream_latency_ms = await upstream_call_with_retry(
            selected_model=selected_model,
            messages=messages,
            target_info=target_info,
            forward_payload=forward_payload,
            is_stream=False,
            max_retries=max_channel_retries,
        )
    except UpstreamCallFailed as fail:
        target_info = fail.target_info
        upstream_latency_ms = fail.upstream_latency_ms
        log_upstream_call(
            request_id=request_id, selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            api_base=target_info["api_base"],
            status_code=502, ok=False, latency_ms=upstream_latency_ms,
            error=sanitize_error(fail.exc), config_version=config_version,
            config_source=config_source, router_trace_id=router_trace_id,
        )
        if call_log_created:
            await calllog.update_call_log(request_id=request_id, status=2,
                error_code="upstream_error", error_msg=sanitize_error(fail.exc)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
                upstream_latency_ms=int(upstream_latency_ms),
                request_preview=build_db_request_preview(messages, None),
            )
        log_event(
            logger, logging.ERROR, "chatFailed",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            selectedModel=selected_model,
            provider=target_info["provider_slug"],
            routingTier=(route_result or {}).get("routing_tier"),
            totalScore=(route_result or {}).get("total_score_0_10"),
            isStream=False,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="upstream",
            errorCode="upstream_error",
            errorDetail=sanitize_error(fail.exc)[:256],
            upstreamLatencyMs=round(upstream_latency_ms, 2),
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        raise HTTPException(status_code=502, detail="upstream service error") from fail.exc

    response_json = litellm_response.model_dump(exclude_none=True)
    completion_payload = _completion_from_chat_response(response_json)
    completion_payload["model"] = selected_model

    log_upstream_call(
        request_id=request_id, selected_model=selected_model,
        provider_slug=target_info["provider_slug"],
        upstream_model=target_info["upstream_model"],
        api_base=target_info["api_base"],
        status_code=200, ok=True, latency_ms=upstream_latency_ms,
        config_version=config_version, config_source=config_source,
        router_trace_id=router_trace_id,
    )

    if call_log_created:
        usage = response_json.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached_tokens = extract_cached_tokens(usage)
        total_tokens = usage.get("total_tokens", 0)
        user_prices = get_config_manager().load().get("model_prices", {}).get(selected_model, {})
        cost, provider_cost, cost_detail = compute_cost(
            prompt_tokens, completion_tokens, cached_tokens,
            user_input_price=user_prices.get("input", 0),
            user_output_price=user_prices.get("output", 0),
            user_cached_price=user_prices.get("cached_input", 0),
            provider_input_price=target_info.get("input_price_per_million", 0),
            provider_output_price=target_info.get("output_price_per_million", 0),
            provider_cached_price=target_info.get("cached_input_price_per_million", 0),
        )
        full_response_text = ""
        try:
            choices_out = completion_payload.get("choices") or []
            if choices_out:
                full_response_text = str(choices_out[0].get("text") or "")
        except Exception:
            full_response_text = ""
        await calllog.update_call_log( request_id=request_id, status=1,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            provider_cost=provider_cost,
            cost_detail=cost_detail,
            duration_ms=int((time.monotonic() - t_start) * 1000),
            upstream_latency_ms=int(upstream_latency_ms),
            request_preview=build_db_request_preview(messages, full_response_text),
        )
        log_event(
            logger, logging.INFO, "chatComplete",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            selectedModel=selected_model,
            provider=target_info["provider_slug"],
            routingTier=(route_result or {}).get("routing_tier"),
            totalScore=(route_result or {}).get("total_score_0_10"),
            isStream=False,
            messagesCount=messages_count,
            inputHash=input_hash,
            promptTokens=prompt_tokens,
            completionTokens=completion_tokens,
            cachedTokens=cached_tokens,
            totalTokens=total_tokens,
            cost=cost,
            providerCost=provider_cost,
            upstreamLatencyMs=round(upstream_latency_ms, 2),
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )

    return JSONResponse(content=completion_payload)
