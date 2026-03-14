"""OpenAI-compatible router endpoints."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.crypto import decrypt_api_key
from router_service.config import get_settings
from router_service.dependencies import get_db_session, get_router_key_context
from router_service.schemas import (
    OpenAIModelCard,
    OpenAIModelListResponse,
    RouterChatCompletionRequest,
    RouterCompletionRequest,
)
from router_service.services import (
    ProviderClientService,
    RouteCandidate,
    RouterBillingService,
    RouterKeyContext,
    RouterQuotaExceededError,
    RouterUpstreamError,
    RoutingService,
    SmartRouterService,
)

router = APIRouter(tags=["openai-compat"])


def _extract_chat_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for choice in payload.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            parts.append(message["content"])
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            parts.append(delta["content"])
    return "".join(parts)


def _completion_from_chat_response(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    converted = []
    for index, choice in enumerate(choices):
        message = choice.get("message") if isinstance(choice, dict) else None
        converted.append(
            {
                "text": message.get("content", "") if isinstance(message, dict) else "",
                "index": choice.get("index", index) if isinstance(choice, dict) else index,
                "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
                "logprobs": None,
            }
        )
    return {
        "id": payload.get("id"),
        "object": "text_completion",
        "created": payload.get("created"),
        "model": payload.get("model"),
        "choices": converted,
        "usage": payload.get("usage"),
    }


def _completion_chunk_from_chat_chunk(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    converted = []
    for index, choice in enumerate(choices):
        delta = choice.get("delta") if isinstance(choice, dict) else None
        converted.append(
            {
                "text": delta.get("content", "") if isinstance(delta, dict) else "",
                "index": choice.get("index", index) if isinstance(choice, dict) else index,
                "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
                "logprobs": None,
            }
        )
    return {
        "id": payload.get("id"),
        "object": "text_completion",
        "created": payload.get("created"),
        "model": payload.get("model"),
        "choices": converted,
    }


def _build_chat_response(
    *,
    model: str,
    content: str,
    usage_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage_payload,
    }


def _extract_messages_from_prompt(prompt: str | list[str]) -> list[dict[str, Any]]:
    if isinstance(prompt, list):
        content = "\n".join(str(item) for item in prompt)
    else:
        content = str(prompt)
    return [{"role": "user", "content": content}]


def _strip_forwarded_fields(payload: dict[str, Any], *removed: str) -> dict[str, Any]:
    stripped = dict(payload)
    for key in removed:
        stripped.pop(key, None)
    return stripped


def _max_candidate_price(
    candidates: list[RouteCandidate],
    field_name: str,
) -> float | None:
    prices = [
        float(value)
        for candidate in candidates
        if (value := getattr(candidate, field_name, None)) is not None
    ]
    return max(prices) if prices else None


async def _decrypt_provider_key(candidate: RouteCandidate) -> str:
    master_key = get_settings().provider_secret_master_key
    if not master_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Router secret master key is not configured",
        )
    return decrypt_api_key(
        candidate.encrypted_api_key[0],
        candidate.encrypted_api_key[1],
        candidate.encrypted_api_key[2],
        master_key,
    )


async def _resolve_model_and_candidates(
    db: AsyncSession,
    *,
    model_name: str,
    messages: list[dict[str, Any]],
) -> tuple[str, list[RouteCandidate], dict[str, Any] | None]:
    settings = get_settings()
    requested_model = model_name.strip()
    resolved_model = requested_model
    smart_router_meta = None

    if settings.SMART_ROUTER_ENABLED and requested_model == settings.SMART_ROUTER_ALIAS:
        resolved_model, decision = await SmartRouterService.resolve_model(db, messages)
        smart_router_meta = {
            "difficulty": decision.difficulty,
            "source": decision.source,
        }

    provider_hint, logical_model = RoutingService.split_provider_prefix(resolved_model)
    candidates = await RoutingService.build_candidates(
        db,
        model_name=logical_model,
        provider_hint=provider_hint,
    )
    if not candidates and smart_router_meta and settings.SMART_ROUTER_FALLBACK_MODEL.strip():
        fallback_provider_hint, fallback_model = RoutingService.split_provider_prefix(
            settings.SMART_ROUTER_FALLBACK_MODEL.strip()
        )
        fallback_candidates = await RoutingService.build_candidates(
            db,
            model_name=fallback_model,
            provider_hint=fallback_provider_hint,
        )
        if fallback_candidates:
            smart_router_meta["fallback_model"] = fallback_model
            return fallback_model, fallback_candidates, smart_router_meta
    return logical_model, candidates, smart_router_meta


async def _invoke_chat_completion(
    db: AsyncSession,
    *,
    context: RouterKeyContext,
    request_payload: dict[str, Any],
    requested_model: str,
    endpoint: str,
    completion_mode: bool = False,
) -> JSONResponse | StreamingResponse:
    messages = request_payload["messages"]
    resolved_model, candidates, smart_router_meta = await _resolve_model_and_candidates(
        db,
        model_name=requested_model,
        messages=messages,
    )
    if not candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No route candidate found")

    request_id = uuid.uuid4().hex
    reservation_input_price = _max_candidate_price(candidates, "input_price_per_m")
    reservation_output_price = _max_candidate_price(candidates, "output_price_per_m")
    try:
        await RouterBillingService.reserve_usage(
            db,
            context=context,
            request_id=request_id,
            endpoint=endpoint,
            requested_model=requested_model,
            resolved_model=resolved_model,
            request_payload=request_payload,
            input_price_per_m=reservation_input_price,
            output_price_per_m=reservation_output_price,
        )
    except RouterQuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    forward_payload = _strip_forwarded_fields(request_payload, "model", "messages")
    settings = get_settings()
    request_started_at = time.perf_counter()
    last_error = None
    last_candidate = None
    terminal_http_exception = None
    for candidate in candidates:
        last_candidate = candidate
        try:
            upstream_api_key = await _decrypt_provider_key(candidate)
            start = time.perf_counter()
            upstream_result = await ProviderClientService.chat_completion(
                model=candidate.provider_model_name,
                messages=messages,
                api_key=upstream_api_key,
                api_base=candidate.api_base_url,
                stream=bool(request_payload.get("stream")),
                extra_payload=forward_payload,
                timeout=settings.ROUTER_STREAM_TIMEOUT_SECONDS,
            )
        except HTTPException as exc:
            terminal_http_exception = exc
            last_error = exc
            break
        except RouterUpstreamError as exc:
            last_error = exc
            continue

        if request_payload.get("stream"):
            async def stream_events():
                collected_text: list[str] = []
                usage_payload: dict[str, Any] | None = None
                status_code = 200
                error_message = None
                try:
                    async for chunk in upstream_result:
                        normalized = ProviderClientService.normalize_payload(chunk)
                        if normalized.get("usage"):
                            usage_payload = normalized.get("usage")
                        collected_text.append(_extract_chat_text(normalized))
                        outgoing = (
                            _completion_chunk_from_chat_chunk(normalized)
                            if completion_mode
                            else normalized
                        )
                        yield f"data: {json.dumps(outgoing, ensure_ascii=False)}\n\n"
                except Exception as exc:
                    status_code = 502
                    error_message = str(exc)
                    raise
                finally:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    response_payload = _build_chat_response(
                        model=resolved_model,
                        content="".join(collected_text),
                        usage_payload=usage_payload,
                    )
                    await RouterBillingService.settle_usage(
                        db,
                        context=context,
                        request_id=request_id,
                        endpoint=endpoint,
                        provider_slug=candidate.provider_slug,
                        requested_model=requested_model,
                        resolved_model=resolved_model,
                        request_payload=request_payload,
                        response_payload=response_payload,
                        input_price_per_m=candidate.input_price_per_m,
                        output_price_per_m=candidate.output_price_per_m,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        error_code="upstream_error" if error_message else None,
                        error_message=error_message,
                    )
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream_events(), media_type="text/event-stream")

        normalized = ProviderClientService.normalize_payload(upstream_result)
        latency_ms = int((time.perf_counter() - start) * 1000)
        await RouterBillingService.settle_usage(
            db,
            context=context,
            request_id=request_id,
            endpoint=endpoint,
            provider_slug=candidate.provider_slug,
            requested_model=requested_model,
            resolved_model=resolved_model,
            request_payload=request_payload,
            response_payload=normalized,
            input_price_per_m=candidate.input_price_per_m,
            output_price_per_m=candidate.output_price_per_m,
            status_code=200,
            latency_ms=latency_ms,
        )
        if smart_router_meta:
            normalized.setdefault("router", {}).update(smart_router_meta)
        payload = _completion_from_chat_response(normalized) if completion_mode else normalized
        return JSONResponse(content=payload)

    if last_candidate is not None:
        failure_status = (
            terminal_http_exception.status_code
            if terminal_http_exception is not None
            else status.HTTP_502_BAD_GATEWAY
        )
        failure_message = (
            str(terminal_http_exception.detail)
            if terminal_http_exception is not None
            else str(last_error or "Upstream provider request failed")
        )
        await RouterBillingService.settle_usage(
            db,
            context=context,
            request_id=request_id,
            endpoint=endpoint,
            provider_slug=last_candidate.provider_slug,
            requested_model=requested_model,
            resolved_model=resolved_model,
            request_payload=request_payload,
            response_payload=None,
            input_price_per_m=None,
            output_price_per_m=None,
            status_code=failure_status,
            latency_ms=int((time.perf_counter() - request_started_at) * 1000),
            error_code="routing_error" if terminal_http_exception is not None else "upstream_error",
            error_message=failure_message,
        )

    if terminal_http_exception is not None:
        raise terminal_http_exception

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(last_error or "Upstream provider request failed"),
    )


@router.get("/v1/models", response_model=OpenAIModelListResponse, summary="List router models")
async def list_models(
    context: RouterKeyContext = Depends(get_router_key_context),
    db: AsyncSession = Depends(get_db_session),
) -> OpenAIModelListResponse:
    del context
    items = await RoutingService.list_available_models(db)
    settings = get_settings()
    if settings.SMART_ROUTER_ENABLED:
        items.insert(0, {"id": settings.SMART_ROUTER_ALIAS, "object": "model", "owned_by": "eucal-router"})
    return OpenAIModelListResponse(data=[OpenAIModelCard(**item) for item in items])


@router.post("/v1/chat/completions", summary="Create a chat completion")
async def chat_completions(
    request: RouterChatCompletionRequest,
    context: RouterKeyContext = Depends(get_router_key_context),
    db: AsyncSession = Depends(get_db_session),
):
    payload = request.model_dump(exclude_none=True)
    return await _invoke_chat_completion(
        db,
        context=context,
        request_payload=payload,
        requested_model=request.model,
        endpoint="/v1/chat/completions",
    )


@router.post("/v1/completions", summary="Create a completion")
async def completions(
    request: RouterCompletionRequest,
    context: RouterKeyContext = Depends(get_router_key_context),
    db: AsyncSession = Depends(get_db_session),
):
    payload = request.model_dump(exclude_none=True)
    messages = _extract_messages_from_prompt(request.prompt)
    chat_payload = _strip_forwarded_fields(payload, "prompt", "suffix")
    chat_payload["messages"] = messages
    return await _invoke_chat_completion(
        db,
        context=context,
        request_payload=chat_payload,
        requested_model=request.model,
        endpoint="/v1/completions",
        completion_mode=True,
    )
