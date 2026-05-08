"""POST /v1/responses — OpenAI Responses API compatible endpoint."""

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
from schemas.responses import ResponsesRequest
from services.channel_selector import ChannelRateLimited
from services.responses_convert import (
    ResponsesStreamConverter,
    openai_to_responses_response,
    responses_to_openai_request,
)
from services.routing import route_and_resolve
from services.upstream import strip_think_tags
from utils.billing import compute_cost
from utils.logging_config import build_db_request_preview, get_app_logger, log_upstream_call
from utils.text import compute_input_hash, stringify_message_content

router = APIRouter()
logger = get_app_logger()


@router.post("/v1/responses")
async def responses(
    request: ResponsesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    is_stream = request.stream
    requested_model = str(request.model).strip()
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"responses-{uuid.uuid4().hex[:12]}"
    settings = get_settings()
    calllog = get_calllog_gateway()

    openai_messages, forward_payload = responses_to_openai_request(request)

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
                request_id=request_id, status=2,
                error_code="insufficient_balance", error_msg="余额不足",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise HTTPException(status_code=402, detail="insufficient balance")

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
                request_id=request_id, status=2,
                error_code=exc.error_code, error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise
    except ChannelRateLimited:
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id, status=2,
                error_code="channel_rate_limited",
                error_msg="all channels rate-limited",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise HTTPException(status_code=429, detail="All upstream channels are currently rate-limited.")

    config_version = route_meta.get("config_version")
    config_source = route_meta.get("config_source", "")

    if call_log_created:
        await calllog.update_call_log(
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            config_version=config_version,
            config_source=config_source,
            router_trace_id=router_trace_id,
            messages_count=messages_count,
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
        if call_log_created:
            await calllog.update_call_log(
                request_id=request_id, status=2,
                error_code="upstream_error",
                error_msg=sanitize_error(fail.exc)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
                upstream_latency_ms=int(fail.upstream_latency_ms),
            )
        raise HTTPException(status_code=502, detail="upstream service error") from fail.exc

    # --- Streaming ---
    if is_stream:
        t_stream_start = time.monotonic()
        converter = ResponsesStreamConverter(selected_model)

        async def _stream_responses_sse():
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
                if not converter._finished:
                    if converter._text_started:
                        yield converter._emit_text_done()
                    yield converter._emit_completed()
                stream_ok = True
            except (asyncio.CancelledError, GeneratorExit):
                abort_reason = "client_cancelled"
                raise
            except Exception as exc:
                abort_reason = "stream_error"
                stream_exc = exc
            finally:
                final_latency = (time.monotonic() - t_stream_start) * 1000
                if call_log_created:
                    update_kwargs: dict = {
                        "request_id": request_id,
                        "status": 1 if stream_ok else 4,
                        "duration_ms": int((time.monotonic() - t_start) * 1000),
                        "upstream_latency_ms": int(final_latency),
                        "error_code": None if stream_ok else (
                            "upstream_stream_error" if abort_reason == "stream_error" else "client_aborted"
                        ),
                    }
                    if stream_ok and stream_usage:
                        prompt_tokens = stream_usage.get("prompt_tokens", 0)
                        completion_tokens = stream_usage.get("completion_tokens", 0)
                        cached_tokens = stream_usage.get("cached_tokens", 0)
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
                            cost=cost, provider_cost=provider_cost, cost_detail=cost_detail,
                        )
                    update_coro = calllog.update_call_log(**update_kwargs)
                    if abort_reason == "client_cancelled":
                        update_task = asyncio.ensure_future(update_coro)
                        with contextlib.suppress(asyncio.CancelledError):
                            await asyncio.shield(update_task)
                    else:
                        await update_coro

        return StreamingResponse(
            _stream_responses_sse(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    # --- Non-streaming ---
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

    responses_response = openai_to_responses_response(response_payload, selected_model)

    if call_log_created:
        usage = response_payload.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached_tokens = usage.get("cached_tokens", 0)
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
            request_id=request_id, status=1,
            duration_ms=int((time.monotonic() - t_start) * 1000),
            upstream_latency_ms=int(upstream_latency_ms),
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            cached_tokens=cached_tokens, total_tokens=total_tokens,
            cost=cost, provider_cost=provider_cost, cost_detail=cost_detail,
        )

    return JSONResponse(content=responses_response)
