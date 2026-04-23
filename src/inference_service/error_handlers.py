"""Global exception handlers for inference-service structured error responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.observability import REQUEST_ID_HEADER, get_request_id
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
    @app.exception_handler(InferenceAuthError)
    async def _auth_error(_request: Request, exc: InferenceAuthError) -> JSONResponse:
        return _build_error_response(403, "auth", exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _build_error_response(422, "validation", str(exc))

    @app.exception_handler(InferenceConfigError)
    async def _config_error(_request: Request, exc: InferenceConfigError) -> JSONResponse:
        return _build_error_response(503, "config", exc.message)

    @app.exception_handler(InferenceUnavailableError)
    async def _unavailable_error(
        _request: Request, exc: InferenceUnavailableError
    ) -> JSONResponse:
        return _build_error_response(503, "unavailable", exc.message)

    @app.exception_handler(InferenceTimeoutError)
    async def _timeout_error(
        _request: Request, exc: InferenceTimeoutError
    ) -> JSONResponse:
        return _build_error_response(504, "timeout", exc.message)

    @app.exception_handler(Exception)
    async def _catchall_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled inference error: %s", exc)
        return _build_error_response(500, "model_runtime", "internal inference error")
