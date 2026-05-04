"""Unified logging configuration for router-service.

Three loggers:
- router_service          : general app logs (console + app.log)
- router_service.routing  : routing decision JSONL (routing.jsonl)
- router_service.upstream : upstream call JSONL (upstream.jsonl)
"""

from __future__ import annotations

import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

from common.observability import configure_logging, get_ring_buffer, utc_now_iso

LOGGER_APP = "router_service"
LOGGER_ROUTING = "router_service.routing"
LOGGER_UPSTREAM = "router_service.upstream"
INPUT_PREVIEW_MAX_CHARS = 300
RESPONSE_PREVIEW_MAX_CHARS = 300

# DB-side preview for the route-monitor panel — much larger than the file logs
# because it's the only way to inspect what the user actually sent. Per-message
# content is bounded so a single chat row stays well under MySQL row limits.
DB_PREVIEW_PER_FIELD_MAX_CHARS = 32_768
DB_PREVIEW_MESSAGES_MAX_COUNT = 64

_initialized = False

_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(password\s*[:=]\s*)([^\s,&]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,&]+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^\s,&]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,&]+)"),
    re.compile(r"(?i)(bearer\s+)(sk-[A-Za-z0-9._-]+|[A-Za-z0-9._-]{8,})"),
    re.compile(r"sk-[A-Za-z0-9._-]{8,}"),
]


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON for JSONL files."""

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {}
        if isinstance(record.msg, dict):
            data = record.msg
        else:
            data["message"] = record.getMessage()
        if "timestamp" not in data:
            data["timestamp"] = utc_now_iso()
        return json.dumps(data, ensure_ascii=False, default=str)


def _clear_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _redact_preview(value: str, *, max_chars: int) -> str:
    text = str(value or "")
    for pattern in _SENSITIVE_PATTERNS:

        def _replace(match: re.Match[str]) -> str:
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}[REDACTED]"
            return "[REDACTED]"

        text = pattern.sub(_replace, text)
    return text[:max_chars]


def build_db_request_preview(
    messages: list[dict],
    response_text: str | None,
    *,
    per_field_max: int = DB_PREVIEW_PER_FIELD_MAX_CHARS,
    messages_max: int = DB_PREVIEW_MESSAGES_MAX_COUNT,
) -> dict[str, Any]:
    """Build the JSON blob persisted to api_call_logs.request_preview.

    - Each message content is redacted (sk-*, password=, token=...) and
      individually truncated to per_field_max chars.
    - At most `messages_max` messages are kept (most recent retained).
    - response_text is redacted and truncated to per_field_max chars.
    - Sets is_truncated=True if any field or the message list was clipped.
    """
    is_truncated = False
    msgs_in = list(messages or [])
    if len(msgs_in) > messages_max:
        msgs_in = msgs_in[-messages_max:]
        is_truncated = True

    preview_messages: list[dict[str, Any]] = []
    for msg in msgs_in:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))[:32]
        raw_content = msg.get("content")
        if isinstance(raw_content, str):
            content_str = raw_content
        else:
            try:
                content_str = json.dumps(raw_content, ensure_ascii=False, default=str)
            except Exception:
                content_str = str(raw_content)
        if len(content_str) > per_field_max:
            is_truncated = True
        redacted = _redact_preview(content_str, max_chars=per_field_max)
        preview_messages.append({"role": role, "content": redacted})

    response_redacted: str | None = None
    if response_text:
        if len(str(response_text)) > per_field_max:
            is_truncated = True
        response_redacted = _redact_preview(str(response_text), max_chars=per_field_max)

    return {
        "messages": preview_messages,
        "response_text": response_redacted,
        "is_truncated": is_truncated,
    }


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    *,
    env: str = "development",
    enable_file_logging: bool = False,
    file_max_bytes: int = 50 * 1024 * 1024,
    file_backup_count: int = 5,
    ring_buffer_capacity: int = 2000,
) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    os.makedirs(log_dir, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)

    configure_logging(
        level,
        service_name="router-service",
        env=env,
        log_dir=log_dir,
        enable_file_logging=enable_file_logging,
        file_prefix="app",
        file_max_bytes=file_max_bytes,
        file_backup_count=file_backup_count,
        ring_buffer_capacity=ring_buffer_capacity,
    )

    # --- App logger: inherited JSON stdout/file handlers ---
    app_logger = logging.getLogger(LOGGER_APP)
    app_logger.setLevel(log_level)
    _clear_handlers(app_logger)
    app_logger.propagate = True

    # --- Routing logger: JSONL file ---
    routing_logger = logging.getLogger(LOGGER_ROUTING)
    routing_logger.setLevel(logging.INFO)
    routing_logger.propagate = False
    _clear_handlers(routing_logger)

    routing_handler = RotatingFileHandler(
        os.path.join(log_dir, "routing.jsonl"),
        maxBytes=100 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    routing_handler.setFormatter(JsonLineFormatter())
    routing_logger.addHandler(routing_handler)

    # --- Upstream logger: JSONL file ---
    upstream_logger = logging.getLogger(LOGGER_UPSTREAM)
    upstream_logger.setLevel(logging.INFO)
    upstream_logger.propagate = False
    _clear_handlers(upstream_logger)

    upstream_handler = RotatingFileHandler(
        os.path.join(log_dir, "upstream.jsonl"),
        maxBytes=100 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    upstream_handler.setFormatter(JsonLineFormatter())
    upstream_logger.addHandler(upstream_handler)

    ring = get_ring_buffer()
    if ring is not None:
        routing_logger.addHandler(ring)
        upstream_logger.addHandler(ring)


def get_app_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_APP)


def get_routing_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_ROUTING)


def get_upstream_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_UPSTREAM)


def log_routing_decision(
    *,
    request_id: str,
    requested_model: str,
    scores_0_2: Dict[str, float] | None = None,
    proto_weighted_0_2: float | None = None,
    total_score_0_10: float | None = None,
    score_source: str | None = None,
    routing_tier: int | None = None,
    selected_model: str | None = None,
    input_preview: str = "",
    messages_count: int = 0,
    is_stream: bool = False,
    fallback_routes: list[str] | None = None,
    config_version: int | None = None,
    config_source: str | None = None,
    error_code: str | None = None,
    router_trace_id: str | None = None,
    inference_config_version: int | None = None,
    inference_config_source: str | None = None,
) -> None:
    record: Dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "service": "router-service",
        "event": "routingDecision",
        "request_id": request_id,
        "router_trace_id": router_trace_id,
        "requested_model": requested_model,
        "scores_0_2": scores_0_2,
        "proto_weighted_0_2": round(proto_weighted_0_2, 4)
        if proto_weighted_0_2 is not None
        else None,
        "total_score_0_10": round(total_score_0_10, 4) if total_score_0_10 is not None else None,
        "score_source": score_source,
        "routing_tier": routing_tier,
        "selected_model": selected_model,
        "input_preview": _redact_preview(input_preview, max_chars=INPUT_PREVIEW_MAX_CHARS),
        "messages_count": messages_count,
        "is_stream": is_stream,
        "config_version": config_version,
        "config_source": config_source,
        "inference_config_version": inference_config_version,
        "inference_config_source": inference_config_source,
    }
    if fallback_routes:
        record["fallback_routes"] = fallback_routes
    if error_code:
        record["error_code"] = error_code
    get_routing_logger().info(record)


def log_upstream_call(
    *,
    request_id: str,
    selected_model: str,
    provider_slug: str,
    upstream_model: str,
    api_base: str,
    status_code: int | None = None,
    ok: bool | None = None,
    latency_ms: float | None = None,
    is_stream: bool = False,
    response_preview: str = "",
    error: str | None = None,
    config_version: int | None = None,
    config_source: str | None = None,
    router_trace_id: str | None = None,
) -> None:
    record: Dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "service": "router-service",
        "event": "upstreamCall",
        "request_id": request_id,
        "router_trace_id": router_trace_id,
        "selected_model": selected_model,
        "provider_slug": provider_slug,
        "upstream_model": upstream_model,
        "api_base": api_base,
        "status_code": status_code,
        "ok": ok,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "is_stream": is_stream,
        "response_preview": _redact_preview(response_preview, max_chars=RESPONSE_PREVIEW_MAX_CHARS),
        "config_version": config_version,
        "config_source": config_source,
    }
    if error:
        record["error"] = _redact_preview(str(error), max_chars=500)
    get_upstream_logger().info(record)
