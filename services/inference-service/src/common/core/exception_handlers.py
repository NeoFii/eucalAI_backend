"""Shared FastAPI exception handlers with structured logging."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.core.exceptions import APIException
from common.observability import REQUEST_ID_HEADER, get_request_id, log_event

logger = logging.getLogger("common.exceptions")
VALIDATION_STATUS = status.HTTP_422_UNPROCESSABLE_CONTENT


def _request_id_headers() -> dict[str, str]:
    request_id = get_request_id()
    return {REQUEST_ID_HEADER: request_id} if request_id else {}


def register_exception_handlers(app: FastAPI) -> None:
    """Register shared exception handlers for FastAPI applications."""

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
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
            content={
                "code": exc.status_code,
                "message": exc.detail,
            },
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
        return JSONResponse(
            status_code=VALIDATION_STATUS,
            content={
                "code": VALIDATION_STATUS,
                "message": "Validation error",
                "details": exc.errors(),
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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Internal Server Error",
            },
            headers=_request_id_headers(),
        )
