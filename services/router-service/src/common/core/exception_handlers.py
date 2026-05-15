"""Shared FastAPI exception handlers with structured logging."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.core.exceptions import APIException
from common.observability import REQUEST_ID_HEADER, get_request_id, log_event

logger = logging.getLogger("common.exceptions")
VALIDATION_STATUS = status.HTTP_422_UNPROCESSABLE_CONTENT

_OPENAI_PATHS = frozenset(("/v1/chat/completions", "/v1/responses", "/v1/models"))
_ANTHROPIC_PATHS = frozenset(("/v1/anthropic/messages", "/v1/anthropic/v1/messages"))


def _is_openai_path(request: Request) -> bool:
    return request.url.path in _OPENAI_PATHS


def _is_anthropic_path(request: Request) -> bool:
    return request.url.path in _ANTHROPIC_PATHS


def _openai_error_body(
    status_code: int,
    message: str,
    error_type: str | None = None,
    code: str | None = None,
) -> dict:
    if error_type is None:
        error_type = {
            401: "invalid_request_error",
            403: "invalid_request_error",
            422: "invalid_request_error",
            429: "rate_limit_error",
        }.get(status_code, "server_error")
    if code is None:
        code = {
            401: "invalid_api_key",
            403: "insufficient_permissions",
            429: "rate_limit_exceeded",
        }.get(status_code)
    return {"error": {"message": message, "type": error_type, "param": None, "code": code}}


def _anthropic_error_body(status_code: int, message: str) -> dict:
    error_type = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        422: "invalid_request_error",
        429: "rate_limit_error",
        500: "api_error",
        502: "overloaded_error",
        503: "overloaded_error",
    }.get(status_code, "api_error")
    return {"type": "error", "error": {"type": error_type, "message": message}}


def _request_id_headers() -> dict[str, str]:
    request_id = get_request_id()
    return {REQUEST_ID_HEADER: request_id} if request_id else {}


def register_exception_handlers(app: FastAPI) -> None:
    """Register shared exception handlers for FastAPI applications."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if _is_openai_path(request):
            detail = exc.detail
            if isinstance(detail, dict):
                msg = detail.get("error", {}).get("message", str(detail))
            else:
                msg = str(detail) if detail else "Unknown error"
            return JSONResponse(
                status_code=exc.status_code,
                content=_openai_error_body(exc.status_code, msg),
                headers=_request_id_headers(),
            )
        if _is_anthropic_path(request):
            detail = exc.detail
            if isinstance(detail, dict):
                msg = detail.get("error", {}).get("message", str(detail))
            else:
                msg = str(detail) if detail else "Unknown error"
            return JSONResponse(
                status_code=exc.status_code,
                content=_anthropic_error_body(exc.status_code, msg),
                headers=_request_id_headers(),
            )
        if isinstance(exc, APIException):
            log_event(
                logger,
                logging.WARNING,
                "api_exception",
                service=getattr(request.app.state, "service_name", None),
                request_id=get_request_id(),
                method=request.method,
                path=request.url.path,
                status_code=exc.status_code,
                error_code=getattr(exc, "code", "error"),
                error_type=type(exc).__name__,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.status_code, "message": exc.detail, "data": ""},
                headers=_request_id_headers(),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=_request_id_headers(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        log_event(
            logger,
            logging.WARNING,
            "validation_error",
            service=getattr(request.app.state, "service_name", None),
            request_id=get_request_id(),
            method=request.method,
            path=request.url.path,
            status_code=VALIDATION_STATUS,
            error_type=type(exc).__name__,
            errors=exc.errors(),
        )
        if _is_openai_path(request):
            errors = exc.errors()
            param = None
            parts = []
            for err in errors:
                loc = err.get("loc", ())
                field = ".".join(str(x) for x in loc[1:]) if len(loc) > 1 else None
                if param is None and field:
                    param = field
                parts.append(f"{field or 'body'}: {err.get('msg', 'invalid')}")
            msg = "; ".join(parts) if parts else "Validation failed"
            body = _openai_error_body(VALIDATION_STATUS, msg)
            body["error"]["param"] = param
            return JSONResponse(
                status_code=VALIDATION_STATUS,
                content=body,
                headers=_request_id_headers(),
            )
        if _is_anthropic_path(request):
            errors = exc.errors()
            parts = []
            for err in errors:
                loc = err.get("loc", ())
                field = ".".join(str(x) for x in loc[1:]) if len(loc) > 1 else None
                parts.append(f"{field or 'body'}: {err.get('msg', 'invalid')}")
            msg = "; ".join(parts) if parts else "Validation failed"
            return JSONResponse(
                status_code=VALIDATION_STATUS,
                content=_anthropic_error_body(VALIDATION_STATUS, msg),
                headers=_request_id_headers(),
            )
        return JSONResponse(
            status_code=VALIDATION_STATUS,
            content={
                "code": VALIDATION_STATUS,
                "message": "Validation failed",
                "data": exc.errors(),
            },
            headers=_request_id_headers(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        log_event(
            logger,
            logging.ERROR,
            "unhandled_exception",
            service=getattr(request.app.state, "service_name", None),
            request_id=get_request_id(),
            method=request.method,
            path=request.url.path,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        if _is_openai_path(request):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_openai_error_body(500, "Internal server error"),
                headers=_request_id_headers(),
            )
        if _is_anthropic_path(request):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_anthropic_error_body(500, "Internal server error"),
                headers=_request_id_headers(),
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Internal server error",
                "data": "",
            },
            headers=_request_id_headers(),
        )
