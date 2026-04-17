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
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

LOGGER_APP = "router_service"
LOGGER_ROUTING = "router_service.routing"
LOGGER_UPSTREAM = "router_service.upstream"

_initialized = False


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON for JSONL files."""

    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {}
        if isinstance(record.msg, dict):
            data = record.msg
        else:
            data["message"] = record.getMessage()
        if "ts" not in data:
            data["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    os.makedirs(log_dir, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)

    # --- App logger: console + rotating file ---
    app_logger = logging.getLogger(LOGGER_APP)
    app_logger.setLevel(log_level)
    app_logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    app_logger.addHandler(console_handler)

    app_file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_file_handler.setLevel(log_level)
    app_file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    app_logger.addHandler(app_file_handler)

    # --- Routing logger: JSONL file ---
    routing_logger = logging.getLogger(LOGGER_ROUTING)
    routing_logger.setLevel(logging.INFO)
    routing_logger.propagate = False

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

    upstream_handler = RotatingFileHandler(
        os.path.join(log_dir, "upstream.jsonl"),
        maxBytes=100 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    upstream_handler.setFormatter(JsonLineFormatter())
    upstream_logger.addHandler(upstream_handler)


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
) -> None:
    record: Dict[str, Any] = {
        "request_id": request_id,
        "requested_model": requested_model,
        "scores_0_2": scores_0_2,
        "proto_weighted_0_2": round(proto_weighted_0_2, 4) if proto_weighted_0_2 is not None else None,
        "total_score_0_10": round(total_score_0_10, 4) if total_score_0_10 is not None else None,
        "score_source": score_source,
        "routing_tier": routing_tier,
        "selected_model": selected_model,
        "input_preview": (input_preview or "")[:300],
        "messages_count": messages_count,
        "is_stream": is_stream,
    }
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
) -> None:
    record: Dict[str, Any] = {
        "request_id": request_id,
        "selected_model": selected_model,
        "provider_slug": provider_slug,
        "upstream_model": upstream_model,
        "api_base": api_base,
        "status_code": status_code,
        "ok": ok,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "is_stream": is_stream,
        "response_preview": (response_preview or "")[:300],
    }
    if error:
        record["error"] = str(error)[:500]
    get_upstream_logger().info(record)
