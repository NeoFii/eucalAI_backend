"""Shared observability helpers for service entrypoints and internal calls."""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar, Token
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def configure_logging(log_level: str) -> None:
    """Configure process-wide logging for structured output."""
    logging.basicConfig(
        level=getattr(logging, (log_level or "INFO").upper(), logging.INFO),
        format="%(message)s",
        force=True,
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
    payload = {"event": event, **fields}
    logger.log(
        level,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default),
    )


def install_observability(app: FastAPI, *, service_name: str) -> None:
    """Install request-id propagation and structured access logging."""
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
            log_event(
                access_logger,
                logging.ERROR,
                "request_error",
                service=service_name,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                query=request.url.query or None,
                duration_ms=duration_ms,
                client_ip=client_ip,
                error_type=type(exc).__name__,
            )
            reset_request_id(token)
            raise

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
