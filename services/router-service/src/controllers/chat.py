"""POST /v1/chat/completions — async gateway with inference-service routing."""

from __future__ import annotations

import json
import time
import uuid

import litellm
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from common.observability import get_request_id
from core.dependencies import extract_client_ip, get_channel_selector, get_config_manager, get_rate_limiter, get_settings, require_api_key, require_rate_limit
from gateways.user_identity import ValidatedApiKey
from gateways.calllog import CallLogGateway
from utils.logging_config import get_app_logger, log_upstream_call
from schemas.requests import ChatCompletionRequest
from core.exceptions import RoutingError, sanitize_error
from services.routing import route_and_resolve
from services.channel_selector import ChannelRateLimited
from services.upstream import strip_think_tags
from utils.billing import compute_cost
from utils.text import stringify_message_content

router = APIRouter()
logger = get_app_logger()


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

    input_preview = ""
    if request.messages:
        for msg in reversed(request.messages):
            if str(msg.get("role", "")).lower() == "user":
                input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not input_preview:
            input_preview = stringify_message_content(request.messages[-1].get("content", ""))
    t_start = time.monotonic()
    create_result = await CallLogGateway.create_call_log(
        settings=settings,
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=is_stream,
        ip=extract_client_ip(raw_request),
        status=0,
    )
    call_log_created = create_result is not None

    if principal.balance <= 0:
        if call_log_created:
            await CallLogGateway.update_call_log(
                settings=settings,
                request_id=request_id,
                status=2,
                error_code="insufficient_balance",
                error_msg="余额不足",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise HTTPException(status_code=402, detail="insufficient balance")

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
            await CallLogGateway.update_call_log(
                settings=settings,
                request_id=request_id,
                status=2,
                error_code=exc.error_code,
                error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise
    except ChannelRateLimited:
        if call_log_created:
            await CallLogGateway.update_call_log(
                settings=settings,
                request_id=request_id,
                status=2,
                error_code="channel_rate_limited",
                error_msg="all channels for this model are rate-limited",
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "message": "All upstream channels for this model are currently rate-limited. Please retry later.",
                    "type": "rate_limit_error",
                    "code": "channel_rate_limited",
                }
            },
            headers={"Retry-After": "5"},
        )
    config_version = route_meta.get("config_version")
    config_source = route_meta.get("config_source", "")

    if call_log_created:
        await CallLogGateway.update_call_log(
            settings=settings,
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
            router_trace_id=router_trace_id,
            inference_error_code=route_meta.get("error_code"),
        )

    forward_payload = request.model_dump(
        mode="python",
        exclude={"model", "messages", "stream"},
        exclude_none=True,
    )
    if is_stream:
        forward_payload.setdefault("stream_options", {"include_usage": True})

    t_upstream = time.monotonic()
    channel_slug = target_info.get("channel_slug")
    max_channel_retries = settings.CHANNEL_MAX_RETRIES if channel_slug else 0
    tried_slugs: set[str] = set()

    for _attempt in range(max_channel_retries + 1):
        if channel_slug:
            tried_slugs.add(channel_slug)
        try:
            litellm_response = await litellm.acompletion(
                model=target_info["upstream_model"],
                messages=request.messages,
                api_key=target_info["api_key"],
                api_base=target_info["api_base"],
                base_url=target_info["api_base"],
                custom_llm_provider="openai",
                stream=is_stream,
                timeout=45.0,
                **forward_payload,
            )
            if channel_slug:
                get_channel_selector().report_success(channel_slug)
            account_id = target_info.get("pool_account_id")
            if account_id is not None:
                limiter = get_rate_limiter()
                if limiter is not None:
                    await limiter.check_account(account_id, target_info.get("rpm_limit"))
            break
        except Exception as exc:
            from services.retry_policy import extract_status_code, should_retry
            status_code = extract_status_code(exc)
            if channel_slug:
                get_channel_selector().report_failure(channel_slug)
            if _attempt < max_channel_retries and should_retry(exc, status_code):
                from services.routing import _resolve_target
                config = get_config_manager().load()
                try:
                    target_info = await _resolve_target(
                        selected_model, config,
                        excluded_slugs=frozenset(tried_slugs),
                        retry_tier=_attempt + 1,
                    )
                    channel_slug = target_info.get("channel_slug")
                    t_upstream = time.monotonic()
                    logger.warning(
                        "retrying upstream call (attempt %d/%d) for %s, switching to %s",
                        _attempt + 1, max_channel_retries,
                        selected_model, channel_slug or target_info["provider_slug"],
                    )
                    continue
                except Exception:
                    pass
            upstream_latency_ms = (time.monotonic() - t_upstream) * 1000
            log_upstream_call(
                request_id=request_id,
                selected_model=selected_model,
                provider_slug=target_info["provider_slug"],
                upstream_model=target_info["upstream_model"],
                api_base=target_info["api_base"],
                status_code=502, ok=False,
                latency_ms=upstream_latency_ms,
                is_stream=is_stream,
                error=sanitize_error(exc),
                config_version=config_version,
                config_source=config_source,
                router_trace_id=router_trace_id,
            )
            if call_log_created:
                await CallLogGateway.update_call_log(
                    settings=settings,
                    request_id=request_id,
                    status=2,
                    error_code="upstream_error",
                    error_msg=sanitize_error(exc)[:512],
                    duration_ms=int((time.monotonic() - t_start) * 1000),
                )
            raise HTTPException(status_code=502, detail="upstream service error") from exc
    upstream_latency_ms = (time.monotonic() - t_upstream) * 1000

    headers = {
        "X-Router-Selected-Model": selected_model,
        "X-Router-Provider": target_info["provider_slug"],
        "X-Router-Config-Version": str(config_version) if config_version is not None else "local",
        "X-Router-Config-Source": config_source,
    }
    if is_stream:
        async def _stream_sse():
            collected_content = ""
            stream_usage = {}
            stream_ok = False
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
                        psf = delta.get("provider_specific_fields")
                        if isinstance(psf, dict):
                            psf.pop("reasoning_content", None)
                        dc = delta.get("content")
                        if isinstance(dc, str):
                            collected_content += dc
                    yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                stream_ok = True
            finally:
                final_latency = (time.monotonic() - t_upstream) * 1000
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
                        "settings": settings,
                        "request_id": request_id,
                        "status": final_status,
                        "duration_ms": int((time.monotonic() - t_start) * 1000),
                        "error_code": "client_aborted" if not stream_ok else None,
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
                            cost=cost,
                            provider_cost=provider_cost,
                            cost_detail=cost_detail,
                        )
                    await CallLogGateway.update_call_log(**update_kwargs)

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
        await CallLogGateway.update_call_log(
            settings=settings,
            request_id=request_id,
            status=1,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            provider_cost=provider_cost,
            cost_detail=cost_detail,
            duration_ms=int((time.monotonic() - t_start) * 1000),
        )

    return JSONResponse(content=response_payload, headers=headers)
