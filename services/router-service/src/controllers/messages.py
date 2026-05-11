"""POST /v1/messages — Anthropic Messages API compatible endpoint."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from common.observability import get_request_id, log_event
from core.dependencies import (
    extract_client_ip,
    get_calllog_gateway,
    get_config_manager,
    get_settings,
    require_api_key,
    require_rate_limit,
)
from core.exceptions import RoutingError, sanitize_error
from gateways.user_identity import ValidatedApiKey
from schemas.anthropic import AnthropicMessagesRequest
from services.anthropic_convert import (
    AnthropicStreamConverter,
    anthropic_to_openai_request,
    openai_to_anthropic_response,
)
from services.channel_selector import ChannelRateLimited
from services.routing import route_and_resolve
from services.upstream import strip_think_tags
from utils.billing import compute_cost, extract_cached_tokens
from utils.logging_config import build_db_request_preview, get_app_logger, log_upstream_call
from utils.text import compute_input_hash, stringify_message_content

router = APIRouter()
logger = get_app_logger()


def _anthropic_error(status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )

@router.post("/v1/messages")
async def messages(
    request: AnthropicMessagesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    is_stream = request.stream
    requested_model = str(request.model).strip()
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"messages-{uuid.uuid4().hex[:12]}"
    settings = get_settings()
    calllog = get_calllog_gateway()

    # Convert Anthropic request to OpenAI format
    openai_messages, forward_payload = anthropic_to_openai_request(request)

    input_preview = ""
    for msg in reversed(openai_messages):
        if str(msg.get("role", "")).lower() == "user":
            input_preview = stringify_message_content(msg.get("content", ""))
            break
    if not input_preview and openai_messages:
        input_preview = stringify_message_content(openai_messages[-1].get("content", ""))
    messages_count = len(openai_messages)
    input_hash = compute_input_hash(openai_messages)
    t_start = time.monotonic()

    create_result = await calllog.create_call_log(
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=is_stream,
        ip=extract_client_ip(raw_request),
        input_hash=input_hash,
        status=0,
    )
    call_log_created = create_result is not None

    if principal.balance <= 0:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=2,
                error_code="insufficient_balance",
                error_msg="余额不足",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        return _anthropic_error(402, "invalid_request_error", "insufficient balance")

    affinity_key = raw_request.headers.get("x-conversation-id")

    try:
        selected_model, target_info, route_result, route_meta = await route_and_resolve(
            requested_model=requested_model,
            messages=openai_messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=messages_count,
            is_stream=is_stream,
            affinity_key=affinity_key or None,
        )
    except RoutingError as exc:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=2,
                error_code=exc.error_code,
                error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        return _anthropic_error(exc.status_code, "invalid_request_error", str(exc.detail))
    except ChannelRateLimited:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=2,
                error_code="channel_rate_limited",
                error_msg="all channels rate-limited",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        return _anthropic_error(429, "rate_limit_error", "All upstream channels are currently rate-limited. Please retry later.")

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
        await calllog.update_call_log(
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            config_version=config_version,
            config_source=config_source,
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

    if is_stream:
        forward_payload.setdefault("stream_options", {"include_usage": True})

    from services.upstream_caller import UpstreamCallFailed, upstream_call_with_retry

    max_channel_retries = settings.CHANNEL_MAX_RETRIES if target_info.get("channel_slug") else 0
    try:
        litellm_response, target_info, upstream_latency_ms = await upstream_call_with_retry(
            selected_model=selected_model,
            messages=openai_messages,
            target_info=target_info,
            forward_payload=forward_payload,
            is_stream=is_stream,
            max_retries=max_channel_retries,
        )
    except UpstreamCallFailed as fail:
        target_info = fail.target_info
        upstream_latency_ms = fail.upstream_latency_ms
        log_upstream_call(
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            api_base=target_info["api_base"],
            status_code=502, ok=False,
            latency_ms=upstream_latency_ms,
            is_stream=is_stream,
            error=sanitize_error(fail.exc),
            config_version=config_version,
            config_source=config_source,
            router_trace_id=router_trace_id,
        )
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=2,
                error_code="upstream_error",
                error_msg=sanitize_error(fail.exc)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
                upstream_latency_ms=int(upstream_latency_ms),
            )
        return _anthropic_error(502, "api_error", "upstream service error")

    # --- Streaming response ---
    if is_stream:
        t_stream_start = time.monotonic()
        converter = AnthropicStreamConverter(selected_model)

        async def _stream_anthropic_sse():
            collected_content = ""
            stream_usage = {}
            stream_ok = False
            abort_reason: str | None = None
            stream_exc: BaseException | None = None
            try:
                async for chunk in litellm_response:
                    chunk_dict = chunk.model_dump(exclude_none=True)
                    chunk_dict["model"] = selected_model
                    chunk_usage = chunk_dict.get("usage")
                    if chunk_usage:
                        stream_usage = chunk_usage
                    choices = chunk_dict.get("choices") or []
                    for c in choices:
                        delta = c.get("delta") or {}
                        dc = delta.get("content")
                        if isinstance(dc, str):
                            collected_content += dc
                    sse_events = converter.convert_chunk(chunk_dict)
                    if sse_events:
                        yield sse_events
                # If stream ended without a finish_reason, force close
                if not converter._finished:
                    yield converter._emit_finish("end_turn")
                stream_ok = True
            except (asyncio.CancelledError, GeneratorExit):
                abort_reason = "client_cancelled"
                raise
            except Exception as exc:
                abort_reason = "stream_error"
                stream_exc = exc
            finally:
                final_latency = (time.monotonic() - t_stream_start) * 1000
                log_upstream_call(
                    request_id=request_id,
                    selected_model=selected_model,
                    provider_slug=target_info["provider_slug"],
                    upstream_model=target_info["upstream_model"],
                    api_base=target_info["api_base"],
                    status_code=200 if stream_ok else 502,
                    ok=stream_ok,
                    latency_ms=final_latency,
                    is_stream=True,
                    response_preview=collected_content[:300],
                    config_version=config_version,
                    config_source=config_source,
                    router_trace_id=router_trace_id,
                )
                if call_log_created:
                    final_status = 1 if stream_ok else 4
                    update_kwargs: dict = {
                        "request_id": request_id,
                        "status": final_status,
                        "duration_ms": int((time.monotonic() - t_start) * 1000),
                        "upstream_latency_ms": int(final_latency),
                        "request_preview": build_db_request_preview(openai_messages, collected_content),
                        "error_code": None if stream_ok else (
                            "upstream_stream_error" if abort_reason == "stream_error" else "client_aborted"
                        ),
                    }
                    if abort_reason == "stream_error" and stream_exc is not None:
                        update_kwargs["error_msg"] = sanitize_error(stream_exc)[:512]
                    if stream_ok and stream_usage:
                        prompt_tokens = stream_usage.get("prompt_tokens", 0)
                        completion_tokens = stream_usage.get("completion_tokens", 0)
                        cached_tokens = extract_cached_tokens(stream_usage)
                        total_tokens = stream_usage.get("total_tokens", 0)
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
                        update_kwargs.update(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            cached_tokens=cached_tokens,
                            total_tokens=total_tokens,
                            cost=cost,
                            provider_cost=provider_cost,
                            cost_detail=cost_detail,
                        )
                    update_coro = calllog.update_call_log(**update_kwargs)
                    if abort_reason == "client_cancelled":
                        update_task = asyncio.ensure_future(update_coro)
                        with contextlib.suppress(asyncio.CancelledError):
                            await asyncio.shield(update_task)
                    else:
                        await update_coro

        return StreamingResponse(
            _stream_anthropic_sse(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    # --- Non-streaming response ---
    response_payload = litellm_response.model_dump(exclude_none=True)
    response_payload["model"] = selected_model

    choices = response_payload.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and "<think>" in content:
                message["content"] = strip_think_tags(content)

    log_upstream_call(
        request_id=request_id,
        selected_model=selected_model,
        provider_slug=target_info["provider_slug"],
        upstream_model=target_info["upstream_model"],
        api_base=target_info["api_base"],
        status_code=200, ok=True,
        latency_ms=upstream_latency_ms,
        is_stream=False,
        response_preview=str((choices[0].get("message") or {}).get("content", ""))[:300] if choices else "",
        config_version=config_version,
        config_source=config_source,
        router_trace_id=router_trace_id,
    )

    anthropic_response = openai_to_anthropic_response(response_payload, selected_model)

    if call_log_created:
        usage = response_payload.get("usage") or {}
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
        await calllog.update_call_log(
            request_id=request_id,
            status=1,
            duration_ms=int((time.monotonic() - t_start) * 1000),
            upstream_latency_ms=int(upstream_latency_ms),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            provider_cost=provider_cost,
            cost_detail=cost_detail,
            request_preview=build_db_request_preview(openai_messages, str(anthropic_response.get("content", [{}])[0].get("text", ""))[:300]),
        )

    return JSONResponse(content=anthropic_response)
