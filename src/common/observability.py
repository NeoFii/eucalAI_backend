"""Shared observability helpers for service entrypoints and internal calls."""

from __future__ import annotations

import inspect
import json
import logging
import sys
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonLogFormatter(logging.Formatter):
    """Format log records as a single JSON object with required service fields."""

    def __init__(self, *, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        structured = getattr(record, "structured_fields", None)
        fields = dict(structured) if isinstance(structured, dict) else {}
        event = fields.pop("event", getattr(record, "event", "log"))
        service = fields.pop("service", self.service_name)
        request_id = fields.pop("request_id", get_request_id())

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "service": service,
            "event": event,
            "level": record.levelname,
            "request_id": request_id,
            "logger": record.name,
        }

        if structured is None:
            payload["message"] = record.getMessage()
        elif "message" in fields:
            payload["message"] = fields.pop("message")

        payload.update(fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def configure_logging(
    log_level: str,
    *,
    service_name: str = "service",
    log_dir: str | None = None,
    enable_file_logging: bool = False,
    file_prefix: str | None = None,
    file_max_bytes: int = 50 * 1024 * 1024,
    file_backup_count: int = 5,
    force: bool = True,
) -> None:
    """Configure process-wide structured JSON logging."""
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    formatter = JsonLogFormatter(service_name=service_name)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if enable_file_logging and log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        prefix = file_prefix or service_name
        handlers.append(
            RotatingFileHandler(
                Path(log_dir) / f"{prefix}.log",
                maxBytes=file_max_bytes,
                backupCount=file_backup_count,
                encoding="utf-8",
            )
        )

    for handler in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)

    root = logging.getLogger()
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    logging.captureWarnings(True)


def parse_bool_env(value: str | bool | None, *, default: bool = False) -> bool:
    """Parse common boolean env/config values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging_from_settings(settings: Any) -> None:
    """Configure logging from a settings object exposing LOG_* fields."""
    configure_logging(
        getattr(settings, "LOG_LEVEL", "INFO"),
        service_name=getattr(settings, "SERVICE_NAME", "service"),
        log_dir=getattr(settings, "LOG_DIR", None),
        enable_file_logging=parse_bool_env(getattr(settings, "LOG_TO_FILE", False)),
        file_prefix=getattr(settings, "LOG_FILE_PREFIX", None),
        file_max_bytes=int(getattr(settings, "LOG_FILE_MAX_BYTES", 50 * 1024 * 1024)),
        file_backup_count=int(getattr(settings, "LOG_FILE_BACKUP_COUNT", 5)),
    )


def set_request_id(request_id: str) -> Token:
    """Store the current request id in a context variable."""
    return _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Return the current request id when present."""
    return _request_id_var.get()


def reset_request_id(token: Token) -> None:
    """Reset the request id context to its previous value."""
    _request_id_var.reset(token)


def _json_default(value: Any) -> str:
    return str(value)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a structured JSON log event."""
    exc_info = fields.pop("exc_info", None)
    logger.log(
        level,
        event,
        extra={"structured_fields": {"event": event, **fields}},
        exc_info=exc_info,
    )


def install_observability(app: FastAPI, *, service_name: str) -> None:
    """Install request-id propagation and structured access logging."""
    app.state.service_name = service_name
    access_logger = logging.getLogger(f"{service_name}.access")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = set_request_id(request_id)
        request.state.request_id = request_id
        started_at = perf_counter()
        client_ip = request.client.host if request.client else None

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            exception_handler = app.exception_handlers.get(Exception)
            if exception_handler is not None:
                response = exception_handler(request, exc)
                if inspect.isawaitable(response):
                    response = await response
                if not isinstance(response, Response):
                    response = JSONResponse(
                        status_code=500,
                        content={"detail": "Internal Server Error"},
                    )
            else:
                log_event(
                    logging.getLogger("common.exceptions"),
                    logging.ERROR,
                    "unhandled_exception",
                    service=service_name,
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Internal Server Error"},
                )
            response.headers.setdefault(REQUEST_ID_HEADER, request_id)
            log_event(
                access_logger,
                logging.ERROR,
                "request_error",
                service=service_name,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                error_type=type(exc).__name__,
            )
            reset_request_id(token)
            return response

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        log_event(
            access_logger,
            logging.INFO,
            "request_complete",
            service=service_name,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=client_ip,
        )
        reset_request_id(token)
        return response
