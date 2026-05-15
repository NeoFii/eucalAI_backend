"""POST /v1/chat/completions — async gateway with inference-service routing."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from common.observability import get_request_id, log_event
from core.dependencies import extract_client_ip, get_calllog_gateway, get_config_manager, get_settings, require_api_key, require_rate_limit
from gateways.user_identity import ValidatedApiKey
from utils.logging_config import build_db_request_preview, get_app_logger, log_upstream_call
from schemas.requests import ChatCompletionRequest
from core.exceptions import RoutingError, sanitize_error
from services.routing import route_and_resolve
from services.channel_selector import ChannelRateLimited
from services.upstream import strip_think_tags
from utils.billing import compute_cost, extract_cached_tokens
from utils.text import compute_input_hash, stringify_message_content

router = APIRouter()
logger = get_app_logger()


def _openai_error(
    status_code: int,
    message: str,
    error_type: str | None = None,
    code: str | None = None,
) -> JSONResponse:
    if error_type is None:
        error_type = {
            401: "invalid_request_error",
            402: "invalid_request_error",
            403: "invalid_request_error",
            429: "rate_limit_error",
        }.get(status_code, "server_error")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": code}},
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    is_stream = request.stream
    requested_model = str(request.model).strip()
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"chat-{uuid.uuid4().hex[:12]}"
    settings = get_settings()
    calllog = get_calllog_gateway()

    input_preview = ""
    if request.messages:
        for msg in reversed(request.messages):
            if str(msg.get("role", "")).lower() == "user":
                input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not input_preview:
            input_preview = stringify_message_content(request.messages[-1].get("content", ""))
    messages_count = len(request.messages or [])
    input_hash = compute_input_hash(list(request.messages or []))
    t_start = time.monotonic()
    create_result = await calllog.create_call_log(
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=is_stream,
        ip=extract_client_ip(raw_request),
        input_hash=input_hash,
    )
    call_log_created = create_result is not None

    if principal.balance <= 0:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=402,
                error_code="insufficient_balance",
                error_msg="余额不足",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        return _openai_error(402, "insufficient balance", code="insufficient_balance")

    affinity_key = raw_request.headers.get("x-conversation-id") or getattr(request, "user", None)

    try:
        selected_model, target_info, route_result, route_meta = await route_and_resolve(
            requested_model=requested_model,
            messages=request.messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=len(request.messages),
            is_stream=is_stream,
            affinity_key=affinity_key or None,
        )
    except RoutingError as exc:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=exc.status_code,
                error_code=exc.error_code,
                error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        log_event(
            logger, logging.WARNING, "chatFailed",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            isStream=is_stream,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="classify",
            errorCode=exc.error_code,
            errorDetail=str(exc.detail)[:256],
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        return _openai_error(exc.status_code, str(exc.detail), code=exc.error_code)
    except ChannelRateLimited:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id,
                status=429,
                error_code="channel_rate_limited",
                error_msg="all channels for this model are rate-limited",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        log_event(
            logger, logging.WARNING, "chatFailed",
            requestId=request_id,
            userId=str(principal.user_id),
            requestedModel=requested_model,
            isStream=is_stream,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="rate_limit",
            errorCode="channel_rate_limited",
            errorDetail="all channels for this model are rate-limited",
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        return _openai_error(
            429,
            "All upstream channels are currently rate-limited. Please retry later.",
            "rate_limit_error",
            "rate_limit_exceeded",
        )
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

    forward_payload = request.model_dump(
        mode="python",
        exclude={"model", "messages", "stream"},
        exclude_none=True,
    )
    if is_stream:
        forward_payload.setdefault("stream_options", {"include_usage": True})

    from services.upstream_caller import UpstreamCallFailed, upstream_call_with_retry

    max_channel_retries = settings.CHANNEL_MAX_RETRIES if target_info.get("channel_slug") else 0
    try:
        litellm_response, target_info, upstream_latency_ms = await upstream_call_with_retry(
            selected_model=selected_model,
            messages=request.messages,
            target_info=target_info,
            forward_payload=forward_payload,
            is_stream=is_stream,
            max_retries=max_channel_retries,
            incoming_protocol="openai",
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
                status=502,
                error_code="upstream_error",
                error_msg=sanitize_error(fail.exc)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
                upstream_latency_ms=int(upstream_latency_ms),
                request_preview=build_db_request_preview(
                    list(request.messages or []),
                    None,
                ),
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
            isStream=is_stream,
            messagesCount=messages_count,
            inputHash=input_hash,
            failedAtStage="upstream",
            errorCode="upstream_error",
            errorDetail=sanitize_error(fail.exc)[:256],
            upstreamLatencyMs=round(upstream_latency_ms, 2),
            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
        )
        return _openai_error(502, "upstream service error", "server_error")

    headers = {}
    if is_stream:
        t_stream_start = time.monotonic()

        async def _stream_sse():
            collected_content = ""
            stream_usage = {}
            stream_ok = False
            abort_reason: str | None = None  # None | "client_cancelled" | "stream_error"
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
                        delta.pop("reasoning_content", None)
                        delta.pop("provider_specific_fields", None)
                        c.pop("provider_specific_fields", None)
                        dc = delta.get("content")
                        if isinstance(dc, str):
                            collected_content += dc
                    chunk_dict.pop("provider", None)
                    cu = chunk_dict.get("usage")
                    if isinstance(cu, dict):
                        cu.pop("cost_details", None)
                        cu.pop("is_byok", None)
                    yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                stream_ok = True
            except (asyncio.CancelledError, GeneratorExit):
                # Client disconnected mid-stream. Must re-raise so Starlette
                # closes the underlying connection cleanly; finally still runs.
                abort_reason = "client_cancelled"
                raise
            except Exception as exc:
                # Upstream failure mid-stream (network reset, provider 5xx
                # half-way through SSE, etc). Swallow after finally writes DB.
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
                    final_status = 200 if stream_ok else (502 if abort_reason == "stream_error" else 499)
                    if stream_ok:
                        error_code = None
                    elif abort_reason == "stream_error":
                        error_code = "upstream_stream_error"
                    else:
                        error_code = "client_aborted"
                    update_kwargs: dict = {
                        "request_id": request_id,
                        "status": final_status,
                        "duration_ms": int((time.monotonic() - t_start) * 1000),
                        "upstream_latency_ms": int(final_latency),
                        "request_preview": build_db_request_preview(
                            list(request.messages or []),
                            collected_content,
                        ),
                        "error_code": error_code,
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
                    # On client cancel, the outer await is in a cancelled state and
                    # any further await will re-raise immediately. asyncio.shield
                    # lets the buffer write run to completion in the background even
                    # though we lose the await; CallLogBuffer is in-process memory so
                    # this is safe.
                    update_coro = calllog.update_call_log(**update_kwargs)
                    if abort_reason == "client_cancelled":
                        update_task = asyncio.ensure_future(update_coro)
                        # Buffer task continues running on the event loop after our
                        # await is cancelled; the suppress just stops the second
                        # CancelledError from terminating the finally early.
                        with contextlib.suppress(asyncio.CancelledError):
                            await asyncio.shield(update_task)
                    else:
                        await update_coro
                    if stream_ok and stream_usage:
                        log_event(
                            logger, logging.INFO, "chatComplete",
                            requestId=request_id,
                            userId=str(principal.user_id),
                            requestedModel=requested_model,
                            selectedModel=selected_model,
                            provider=target_info["provider_slug"],
                            routingTier=(route_result or {}).get("routing_tier"),
                            totalScore=(route_result or {}).get("total_score_0_10"),
                            isStream=True,
                            messagesCount=messages_count,
                            inputHash=input_hash,
                            promptTokens=prompt_tokens,
                            completionTokens=completion_tokens,
                            cachedTokens=cached_tokens,
                            totalTokens=total_tokens,
                            cost=cost,
                            providerCost=provider_cost,
                            upstreamLatencyMs=round(final_latency, 2),
                            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
                        )
                    elif abort_reason == "client_cancelled":
                        # log_event is sync (writes to ring buffer + stdout); no await,
                        # so cancellation has already been delivered but does not
                        # interrupt synchronous code.
                        log_event(
                            logger, logging.INFO, "chatAborted",
                            requestId=request_id,
                            userId=str(principal.user_id),
                            requestedModel=requested_model,
                            selectedModel=selected_model,
                            provider=target_info["provider_slug"],
                            routingTier=(route_result or {}).get("routing_tier"),
                            totalScore=(route_result or {}).get("total_score_0_10"),
                            isStream=True,
                            messagesCount=messages_count,
                            inputHash=input_hash,
                            bytesStreamed=len(collected_content),
                            upstreamLatencyMs=round(final_latency, 2),
                            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
                        )
                    elif abort_reason == "stream_error":
                        log_event(
                            logger, logging.ERROR, "chatFailed",
                            requestId=request_id,
                            userId=str(principal.user_id),
                            requestedModel=requested_model,
                            selectedModel=selected_model,
                            provider=target_info["provider_slug"],
                            routingTier=(route_result or {}).get("routing_tier"),
                            totalScore=(route_result or {}).get("total_score_0_10"),
                            isStream=True,
                            messagesCount=messages_count,
                            inputHash=input_hash,
                            failedAtStage="stream",
                            errorCode="upstream_stream_error",
                            errorDetail=sanitize_error(stream_exc)[:256] if stream_exc else "",
                            bytesStreamed=len(collected_content),
                            upstreamLatencyMs=round(final_latency, 2),
                            totalLatencyMs=int((time.monotonic() - t_start) * 1000),
                        )

        return StreamingResponse(
            _stream_sse(),
            media_type="text/event-stream",
            headers={**headers, "cache-control": "no-cache", "connection": "keep-alive"},
        )

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

    response_payload.pop("provider", None)
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        choice.pop("provider_specific_fields", None)
        message = choice.get("message")
        if isinstance(message, dict):
            message.pop("reasoning_content", None)
            message.pop("provider_specific_fields", None)
    resp_usage = response_payload.get("usage")
    if isinstance(resp_usage, dict):
        resp_usage.pop("cost_details", None)
        resp_usage.pop("is_byok", None)

    resp_preview = ""
    try:
        if choices:
            msg = (choices[0].get("message") or {})
            resp_preview = str(msg.get("content") or "")[:300]
    except Exception:
        pass
    log_upstream_call(
        request_id=request_id,
        selected_model=selected_model,
        provider_slug=target_info["provider_slug"],
        upstream_model=target_info["upstream_model"],
        api_base=target_info["api_base"],
        status_code=200, ok=True,
        latency_ms=upstream_latency_ms,
        is_stream=False,
        response_preview=resp_preview,
        config_version=config_version,
        config_source=config_source,
        router_trace_id=router_trace_id,
    )

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
        full_response_text = ""
        if choices:
            try:
                full_response_text = str((choices[0].get("message") or {}).get("content") or "")
            except Exception:
                full_response_text = ""
        await calllog.update_call_log(
            request_id=request_id,
            status=200,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            provider_cost=provider_cost,
            cost_detail=cost_detail,
            duration_ms=int((time.monotonic() - t_start) * 1000),
            upstream_latency_ms=int(upstream_latency_ms),
            request_preview=build_db_request_preview(
                list(request.messages or []),
                full_response_text,
            ),
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

    return JSONResponse(content=response_payload, headers=headers)
