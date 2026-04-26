"""Global exception handlers for inference-service structured error responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.observability import REQUEST_ID_HEADER, get_request_id, log_event
from inference_service.schemas.errors import (
    ClassifyErrorResponse,
    InferenceAuthError,
    InferenceConfigError,
    InferenceTimeoutError,
    InferenceUnavailableError,
)

logger = logging.getLogger("inference_service")


def _build_error_response(
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    request_id = get_request_id()
    body = ClassifyErrorResponse(
        error_code=error_code,
        message=message,
        request_id=request_id,
    )
    headers = {}
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    def _log_inference_error(
        request: Request, status_code: int, error_code: str, exc: Exception
    ) -> None:
        level = logging.ERROR if status_code >= 500 else logging.WARNING
        log_event(
            logger,
            level,
            "inference_error",
            service="inference_service",
            request_id=get_request_id(),
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            error_code=error_code,
            error_type=type(exc).__name__,
            exc_info=status_code >= 500,
        )

    @app.exception_handler(InferenceAuthError)
    async def _auth_error(request: Request, exc: InferenceAuthError) -> JSONResponse:
        _log_inference_error(request, 403, "auth", exc)
        return _build_error_response(403, "auth", exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        _log_inference_error(request, 422, "validation", exc)
        return _build_error_response(422, "validation", str(exc))

    @app.exception_handler(InferenceConfigError)
    async def _config_error(request: Request, exc: InferenceConfigError) -> JSONResponse:
        _log_inference_error(request, 503, "config", exc)
        return _build_error_response(503, "config", exc.message)

    @app.exception_handler(InferenceUnavailableError)
    async def _unavailable_error(request: Request, exc: InferenceUnavailableError) -> JSONResponse:
        _log_inference_error(request, 503, "unavailable", exc)
        return _build_error_response(503, "unavailable", exc.message)

    @app.exception_handler(InferenceTimeoutError)
    async def _timeout_error(request: Request, exc: InferenceTimeoutError) -> JSONResponse:
        _log_inference_error(request, 504, "timeout", exc)
        return _build_error_response(504, "timeout", exc.message)

    @app.exception_handler(Exception)
    async def _catchall_error(request: Request, exc: Exception) -> JSONResponse:
        _log_inference_error(request, 500, "model_runtime", exc)
        return _build_error_response(500, "model_runtime", "internal inference error")
