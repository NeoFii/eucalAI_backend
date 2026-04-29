"""Structured error types and response schema for inference-service."""

from __future__ import annotations

from pydantic import BaseModel


class InferenceAuthError(Exception):
    def __init__(self, message: str = "forbidden") -> None:
        self.message = message
        super().__init__(message)


class InferenceConfigError(Exception):
    def __init__(self, message: str = "config not available") -> None:
        self.message = message
        super().__init__(message)


class InferenceUnavailableError(Exception):
    def __init__(self, message: str = "service not ready") -> None:
        self.message = message
        super().__init__(message)


class InferenceTimeoutError(Exception):
    def __init__(self, message: str = "inference timeout") -> None:
        self.message = message
        super().__init__(message)


class ClassifyErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str | None = None
