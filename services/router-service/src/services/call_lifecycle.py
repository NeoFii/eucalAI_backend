"""Unified call lifecycle orchestration for all relay protocols."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from common.observability import get_request_id, log_event
from core.dependencies import (
    extract_client_ip,
    get_calllog_gateway,
    get_config_manager,
    get_settings,
)
from core.exceptions import RoutingError, sanitize_error
from gateways.user_identity import ValidatedApiKey
from services.channel_selector import ChannelRateLimited
from services.routing import route_and_resolve
from services.upstream_caller import UpstreamCallFailed, upstream_call_with_retry
from utils.billing import compute_cost, extract_cached_tokens
from utils.logging_config import build_db_request_preview, get_app_logger, log_upstream_call
from utils.text import compute_input_hash, stringify_message_content

logger = get_app_logger()

class CallLifecycle:
    """Orchestrates the 8-phase request lifecycle shared by all protocols."""

    def __init__(
        self,
        *,
        adapter: Any,
        principal: ValidatedApiKey,
        raw_request: Request,
        openai_messages: list[dict],
        forward_payload: dict[str, Any],
        is_stream: bool,
        requested_model: str,
        protocol_context: dict[str, Any],
    ) -> None:
        self.adapter = adapter
        self.principal = principal
        self.raw_request = raw_request
        self.openai_messages = openai_messages
        self.forward_payload = forward_payload
        self.is_stream = is_stream
        self.requested_model = requested_model
        self.ctx = protocol_context

        self.request_id = get_request_id() or uuid.uuid4().hex
        self.trace_id = f"{adapter.protocol_name}-{uuid.uuid4().hex[:12]}"
        self.t_start = time.monotonic()
        self.settings = get_settings()
        self.calllog = get_calllog_gateway()

        self.call_log_created = False
        self.selected_model: str = ""
        self.target_info: dict[str, Any] = {}
        self.route_result: dict[str, Any] | None = None
        self.route_meta: dict[str, Any] = {}
        self.config_version: str | None = None
        self.config_source: str = ""
        self.response: Any = None
        self.upstream_latency_ms: float = 0.0

    async def execute(self) -> JSONResponse | StreamingResponse:
        """Run the full lifecycle and return the final HTTP response."""
        await self._init_call_log()

        if error := await self._check_balance():
            return error
        if error := await self._route():
            return error

        if self.is_stream:
            self.forward_payload.setdefault("stream_options", {"include_usage": True})

        if error := await self._call_upstream():
            return error

        if self.is_stream:
            return self._build_stream_response()
        return await self._build_non_stream_response()

    # ------------------------------------------------------------------
    # Phase 1-3: Input normalization + call log creation
    # ------------------------------------------------------------------

    async def _init_call_log(self) -> None:
        self.input_preview = ""
        for msg in reversed(self.openai_messages):
            if str(msg.get("role", "")).lower() == "user":
                self.input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not self.input_preview and self.openai_messages:
            self.input_preview = stringify_message_content(
                self.openai_messages[-1].get("content", "")
            )
        self.messages_count = len(self.openai_messages)
        self.input_hash = compute_input_hash(self.openai_messages)

        result = await self.calllog.create_call_log(
            request_id=self.request_id,
            user_id=self.principal.user_id,
            api_key_id=self.principal.id,
            model_name=self.requested_model,
            is_stream=self.is_stream,
            ip=extract_client_ip(self.raw_request),
            input_hash=self.input_hash,
        )
        self.call_log_created = result is not None

    # ------------------------------------------------------------------
    # Phase 4: Balance check
    # ------------------------------------------------------------------

    async def _check_balance(self) -> JSONResponse | None:
        if self.principal.balance <= 0:
            if self.call_log_created:
                await self.calllog.update_call_log(
                    request_id=self.request_id, status=402,
                    error_code="insufficient_balance", error_msg="余额不足",
                    duration_ms=self._elapsed_ms(),
                )
            return self.adapter.format_error(402, "insufficient balance", error_code="insufficient_balance")
        return None

    # ------------------------------------------------------------------
    # Phase 5: Route and resolve
    # ------------------------------------------------------------------

    async def _route(self) -> JSONResponse | None:
        affinity_key = self.raw_request.headers.get("x-conversation-id")
        try:
            self.selected_model, self.target_info, self.route_result, self.route_meta = (
                await route_and_resolve(
                    requested_model=self.requested_model,
                    messages=self.openai_messages,
                    request_id=self.request_id,
                    input_preview=self.input_preview,
                    messages_count=self.messages_count,
                    is_stream=self.is_stream,
                    affinity_key=affinity_key or None,
                )
            )
        except RoutingError as exc:
            if self.call_log_created:
                await self.calllog.update_call_log(
                    request_id=self.request_id, status=exc.status_code,
                    error_code=exc.error_code, error_msg=str(exc.detail)[:512],
                    duration_ms=self._elapsed_ms(),
                )
            self._log_failed("classify", exc.error_code, str(exc.detail)[:256])
            return self.adapter.format_error(exc.status_code, str(exc.detail), error_code=exc.error_code)
        except ChannelRateLimited:
            if self.call_log_created:
                await self.calllog.update_call_log(
                    request_id=self.request_id, status=429,
                    error_code="channel_rate_limited",
                    error_msg="all channels rate-limited",
                    duration_ms=self._elapsed_ms(),
                )
            self._log_failed("rate_limit", "channel_rate_limited", "all channels rate-limited")
            return self.adapter.format_error(
                429, "All upstream channels are currently rate-limited. Please retry later.",
                error_code="rate_limit_exceeded",
            )

        self.config_version = self.route_meta.get("config_version")
        self.config_source = self.route_meta.get("config_source", "")

        routing_detail = self._build_routing_detail()
        if self.call_log_created:
            ts = (self.route_result or {}).get("total_score_0_10")
            await self.calllog.update_call_log(
                request_id=self.request_id,
                selected_model=self.selected_model,
                provider_slug=self.target_info["provider_slug"],
                upstream_model=self.target_info["upstream_model"],
                config_version=self.config_version,
                config_source=self.config_source,
                inference_config_version=self.route_meta.get("inference_config_version"),
                inference_config_source=self.route_meta.get("inference_config_source"),
                routing_tier=(self.route_result or {}).get("routing_tier"),
                score_source=(self.route_result or {}).get("score_source"),
                total_score_0_10=float(ts) if ts is not None else None,
                router_trace_id=self.trace_id,
                inference_error_code=self.route_meta.get("error_code"),
                messages_count=self.messages_count,
                routing_detail=routing_detail,
            )
        return None

    # ------------------------------------------------------------------
    # Phase 6: Upstream call
    # ------------------------------------------------------------------

    async def _call_upstream(self) -> JSONResponse | StreamingResponse | None:
        max_retries = self.settings.CHANNEL_MAX_RETRIES if self.target_info.get("channel_slug") else 0
        timeout = self.adapter.get_timeout(self.is_stream)
        incoming_protocol = "anthropic" if self.adapter.protocol_name == "messages" else "openai"
        anthropic_request = self.ctx.get("anthropic_request")

        try:
            self.response, self.target_info, self.upstream_latency_ms = (
                await upstream_call_with_retry(
                    selected_model=self.selected_model,
                    messages=self.openai_messages,
                    target_info=self.target_info,
                    forward_payload=self.forward_payload,
                    is_stream=self.is_stream,
                    max_retries=max_retries,
                    timeout=timeout,
                    incoming_protocol=incoming_protocol,
                    anthropic_request=anthropic_request,
                )
            )
        except UpstreamCallFailed as fail:
            self.target_info = fail.target_info
            self.upstream_latency_ms = fail.upstream_latency_ms
            log_upstream_call(
                request_id=self.request_id,
                selected_model=self.selected_model,
                provider_slug=self.target_info["provider_slug"],
                upstream_model=self.target_info["upstream_model"],
                api_base=self.target_info["api_base"],
                status_code=502, ok=False,
                latency_ms=self.upstream_latency_ms,
                is_stream=self.is_stream,
                error=sanitize_error(fail.exc),
                config_version=self.config_version,
                config_source=self.config_source,
                router_trace_id=self.trace_id,
            )
            if self.call_log_created:
                await self.calllog.update_call_log(
                    request_id=self.request_id, status=502,
                    error_code="upstream_error",
                    error_msg=sanitize_error(fail.exc)[:512],
                    duration_ms=self._elapsed_ms(),
                    upstream_latency_ms=int(self.upstream_latency_ms),
                    request_preview=build_db_request_preview(self.openai_messages, None),
                )
            self._log_failed("upstream", "upstream_error", sanitize_error(fail.exc)[:256])
            if self.is_stream and hasattr(self.adapter, "format_error_stream"):
                return StreamingResponse(
                    self.adapter.format_error_stream(self.selected_model),
                    media_type="text/event-stream",
                    headers={"cache-control": "no-cache", "connection": "keep-alive"},
                )
            return self.adapter.format_error(502, "upstream service error", error_code="upstream_error")

        # Detect native Anthropic pass-through after upstream resolves
        if self.adapter.protocol_name == "messages":
            is_native = self.target_info.get("provider_slug") in self.settings.ANTHROPIC_NATIVE_SLUGS
            self.ctx["is_native_passthrough"] = is_native

        return None

    # ------------------------------------------------------------------
    # Phase 7: Stream response
    # ------------------------------------------------------------------

    def _build_stream_response(self) -> StreamingResponse:
        # Native Anthropic pass-through uses a dedicated streaming path
        if self.ctx.get("is_native_passthrough"):
            return StreamingResponse(
                self._stream_native_anthropic(),
                media_type="text/event-stream",
                headers={"cache-control": "no-cache", "connection": "keep-alive"},
            )
        converter = self.adapter.create_stream_converter(self.selected_model, self.ctx)
        return StreamingResponse(
            self._stream_events(converter),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "connection": "keep-alive"},
        )

    async def _stream_events(self, converter: Any) -> AsyncIterator[str]:
        collected_content = ""
        stream_usage: dict = {}
        stream_ok = False
        abort_reason: str | None = None
        stream_exc: BaseException | None = None
        t_stream_start = time.monotonic()
        try:
            async for chunk in self.response:
                chunk_dict = chunk.model_dump(exclude_none=True)
                chunk_dict["model"] = self.selected_model
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
                if converter:
                    sse = converter.convert_chunk(chunk_dict)
                    if sse:
                        yield sse
                else:
                    yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
            # Final event
            if converter:
                final = converter.get_final_event()
                if final:
                    yield final
            else:
                yield "data: [DONE]\n\n"
            stream_ok = True
        except (asyncio.CancelledError, GeneratorExit):
            abort_reason = "client_cancelled"
            raise
        except Exception as exc:
            abort_reason = "stream_error"
            stream_exc = exc
        finally:
            await self._finalize_stream(
                collected_content, stream_usage, stream_ok,
                abort_reason, stream_exc, t_stream_start,
            )

    async def _stream_native_anthropic(self) -> AsyncIterator[str]:
        """Stream raw Anthropic SDK events for native pass-through."""
        collected_content = ""
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        stream_ok = False
        abort_reason: str | None = None
        stream_exc: BaseException | None = None
        t_stream_start = time.monotonic()
        try:
            async for event in self.response:
                event_type = event.type
                event_dict = event.model_dump(exclude_none=True)
                if event_type == "message_start":
                    msg = event_dict.get("message", {})
                    msg["model"] = self.selected_model
                    u = msg.get("usage", {})
                    input_tokens = u.get("input_tokens", 0)
                    cached_tokens = u.get("cache_read_input_tokens", 0)
                elif event_type == "content_block_delta":
                    delta = event_dict.get("delta", {})
                    if delta.get("type") == "text_delta":
                        collected_content += delta.get("text", "")
                elif event_type == "message_delta":
                    u = event_dict.get("usage", {})
                    output_tokens = u.get("output_tokens", output_tokens)
                yield f"event: {event_type}\ndata: {json.dumps(event_dict, ensure_ascii=False)}\n\n"
            stream_ok = True
        except (asyncio.CancelledError, GeneratorExit):
            abort_reason = "client_cancelled"
            raise
        except Exception as exc:
            abort_reason = "stream_error"
            stream_exc = exc
        finally:
            total_tokens = input_tokens + output_tokens
            stream_usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": total_tokens,
            } if stream_ok else {}
            await self._finalize_stream(
                collected_content, stream_usage, stream_ok,
                abort_reason, stream_exc, t_stream_start,
            )

    # ------------------------------------------------------------------
    # Phase 8: Non-stream response
    # ------------------------------------------------------------------

    async def _build_non_stream_response(self) -> JSONResponse:
        response_payload = self.response.model_dump(exclude_none=True)

        # Extract usage and compute cost before adapter transforms the payload
        if self.ctx.get("is_native_passthrough"):
            usage = response_payload.get("usage", {})
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
            cached_tokens = usage.get("cache_read_input_tokens", 0)
            total_tokens = prompt_tokens + completion_tokens
        else:
            usage = response_payload.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cached_tokens = extract_cached_tokens(usage)
            total_tokens = usage.get("total_tokens", 0)

        resp_preview = self._extract_response_preview(response_payload)
        log_upstream_call(
            request_id=self.request_id,
            selected_model=self.selected_model,
            provider_slug=self.target_info["provider_slug"],
            upstream_model=self.target_info["upstream_model"],
            api_base=self.target_info["api_base"],
            status_code=200, ok=True,
            latency_ms=self.upstream_latency_ms,
            is_stream=False,
            response_preview=resp_preview,
            config_version=self.config_version,
            config_source=self.config_source,
            router_trace_id=self.trace_id,
        )

        if self.call_log_created:
            user_prices = get_config_manager().load().get("model_prices", {}).get(self.selected_model, {})
            cost, provider_cost, cost_detail = compute_cost(
                prompt_tokens, completion_tokens, cached_tokens,
                user_input_price=user_prices.get("input", 0),
                user_output_price=user_prices.get("output", 0),
                user_cached_price=user_prices.get("cached_input", 0),
                provider_input_price=self.target_info.get("input_price_per_million", 0),
                provider_output_price=self.target_info.get("output_price_per_million", 0),
                provider_cached_price=self.target_info.get("cached_input_price_per_million", 0),
            )
            await self.calllog.update_call_log(
                request_id=self.request_id, status=200,
                duration_ms=self._elapsed_ms(),
                upstream_latency_ms=int(self.upstream_latency_ms),
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                cached_tokens=cached_tokens, total_tokens=total_tokens,
                cost=cost, provider_cost=provider_cost, cost_detail=cost_detail,
                request_preview=build_db_request_preview(self.openai_messages, resp_preview),
            )
            log_event(
                logger, logging.INFO, "callComplete",
                requestId=self.request_id,
                userId=str(self.principal.user_id),
                requestedModel=self.requested_model,
                selectedModel=self.selected_model,
                provider=self.target_info["provider_slug"],
                routingTier=(self.route_result or {}).get("routing_tier"),
                totalScore=(self.route_result or {}).get("total_score_0_10"),
                isStream=False,
                messagesCount=self.messages_count,
                inputHash=self.input_hash,
                promptTokens=prompt_tokens, completionTokens=completion_tokens,
                cachedTokens=cached_tokens, totalTokens=total_tokens,
                cost=cost, providerCost=provider_cost,
                upstreamLatencyMs=round(self.upstream_latency_ms, 2),
                totalLatencyMs=self._elapsed_ms(),
            )

        return self.adapter.format_non_stream_response(response_payload, self.selected_model, self.ctx)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _finalize_stream(
        self,
        collected_content: str,
        stream_usage: dict,
        stream_ok: bool,
        abort_reason: str | None,
        stream_exc: BaseException | None,
        t_stream_start: float,
    ) -> None:
        final_latency = (time.monotonic() - t_stream_start) * 1000
        log_upstream_call(
            request_id=self.request_id,
            selected_model=self.selected_model,
            provider_slug=self.target_info["provider_slug"],
            upstream_model=self.target_info["upstream_model"],
            api_base=self.target_info["api_base"],
            status_code=200 if stream_ok else 502,
            ok=stream_ok,
            latency_ms=final_latency,
            is_stream=True,
            response_preview=collected_content[:300],
            config_version=self.config_version,
            config_source=self.config_source,
            router_trace_id=self.trace_id,
        )
        if not self.call_log_created:
            return

        final_status = 200 if stream_ok else (502 if abort_reason == "stream_error" else 499)
        error_code = None if stream_ok else (
            "upstream_stream_error" if abort_reason == "stream_error" else "client_aborted"
        )
        update_kwargs: dict[str, Any] = {
            "request_id": self.request_id,
            "status": final_status,
            "duration_ms": self._elapsed_ms(),
            "upstream_latency_ms": int(final_latency),
            "request_preview": build_db_request_preview(self.openai_messages, collected_content),
            "error_code": error_code,
        }
        if abort_reason == "stream_error" and stream_exc is not None:
            update_kwargs["error_msg"] = sanitize_error(stream_exc)[:512]
        if stream_ok and stream_usage:
            prompt_tokens = stream_usage.get("prompt_tokens", 0)
            completion_tokens = stream_usage.get("completion_tokens", 0)
            cached_tokens = stream_usage.get("cached_tokens", 0) or extract_cached_tokens(stream_usage)
            total_tokens = stream_usage.get("total_tokens", 0)
            user_prices = get_config_manager().load().get("model_prices", {}).get(self.selected_model, {})
            cost, provider_cost, cost_detail = compute_cost(
                prompt_tokens, completion_tokens, cached_tokens,
                user_input_price=user_prices.get("input", 0),
                user_output_price=user_prices.get("output", 0),
                user_cached_price=user_prices.get("cached_input", 0),
                provider_input_price=self.target_info.get("input_price_per_million", 0),
                provider_output_price=self.target_info.get("output_price_per_million", 0),
                provider_cached_price=self.target_info.get("cached_input_price_per_million", 0),
            )
            update_kwargs.update(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                cached_tokens=cached_tokens, total_tokens=total_tokens,
                cost=cost, provider_cost=provider_cost, cost_detail=cost_detail,
            )

        update_coro = self.calllog.update_call_log(**update_kwargs)
        if abort_reason == "client_cancelled":
            update_task = asyncio.ensure_future(update_coro)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(update_task)
        else:
            await update_coro

        # Structured log events
        if stream_ok and stream_usage:
            log_event(
                logger, logging.INFO, "callComplete",
                requestId=self.request_id,
                userId=str(self.principal.user_id),
                requestedModel=self.requested_model,
                selectedModel=self.selected_model,
                provider=self.target_info["provider_slug"],
                routingTier=(self.route_result or {}).get("routing_tier"),
                totalScore=(self.route_result or {}).get("total_score_0_10"),
                isStream=True,
                messagesCount=self.messages_count,
                inputHash=self.input_hash,
                promptTokens=prompt_tokens, completionTokens=completion_tokens,
                cachedTokens=cached_tokens, totalTokens=total_tokens,
                cost=cost, providerCost=provider_cost,
                upstreamLatencyMs=round(final_latency, 2),
                totalLatencyMs=self._elapsed_ms(),
            )
        elif abort_reason == "client_cancelled":
            log_event(
                logger, logging.INFO, "callAborted",
                requestId=self.request_id,
                userId=str(self.principal.user_id),
                requestedModel=self.requested_model,
                selectedModel=self.selected_model,
                provider=self.target_info["provider_slug"],
                routingTier=(self.route_result or {}).get("routing_tier"),
                isStream=True,
                messagesCount=self.messages_count,
                bytesStreamed=len(collected_content),
                upstreamLatencyMs=round(final_latency, 2),
                totalLatencyMs=self._elapsed_ms(),
            )
        elif abort_reason == "stream_error":
            log_event(
                logger, logging.ERROR, "callFailed",
                requestId=self.request_id,
                userId=str(self.principal.user_id),
                requestedModel=self.requested_model,
                selectedModel=self.selected_model,
                provider=self.target_info["provider_slug"],
                routingTier=(self.route_result or {}).get("routing_tier"),
                isStream=True,
                messagesCount=self.messages_count,
                failedAtStage="stream",
                errorCode="upstream_stream_error",
                errorDetail=sanitize_error(stream_exc)[:256] if stream_exc else "",
                bytesStreamed=len(collected_content),
                upstreamLatencyMs=round(final_latency, 2),
                totalLatencyMs=self._elapsed_ms(),
            )

    def _build_routing_detail(self) -> dict | None:
        if not self.route_result:
            return None
        return {
            "scores_0_2": self.route_result.get("scores_0_2"),
            "proto_weighted_0_2": self.route_result.get("proto_weighted_0_2"),
            "fallback_routes": self.route_result.get("fallback_routes", []),
            "tier_model_map": self.route_result.get("tier_model_map"),
            "score_bands_raw": self.route_result.get("score_bands_raw"),
        }

    def _extract_response_preview(self, payload: dict) -> str:
        if self.ctx.get("is_native_passthrough"):
            for block in payload.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")[:300]
            return ""
        choices = payload.get("choices") or []
        if choices:
            try:
                return str((choices[0].get("message") or {}).get("content") or "")[:300]
            except Exception:
                pass
        return ""

    def _log_failed(self, stage: str, error_code: str, detail: str) -> None:
        log_event(
            logger, logging.WARNING, "callFailed",
            requestId=self.request_id,
            userId=str(self.principal.user_id),
            requestedModel=self.requested_model,
            selectedModel=self.selected_model or None,
            provider=(self.target_info or {}).get("provider_slug"),
            routingTier=(self.route_result or {}).get("routing_tier"),
            totalScore=(self.route_result or {}).get("total_score_0_10"),
            isStream=self.is_stream,
            messagesCount=self.messages_count,
            inputHash=self.input_hash,
            failedAtStage=stage,
            errorCode=error_code,
            errorDetail=detail,
            totalLatencyMs=self._elapsed_ms(),
        )

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self.t_start) * 1000)
