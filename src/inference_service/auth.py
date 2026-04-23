"""Lightweight shared-secret authentication for inference-service."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header

from inference_service.schemas.errors import InferenceAuthError, InferenceUnavailableError

logger = logging.getLogger("inference_service")


def require_inference_secret(
    x_inference_secret: str | None = Header(default=None),
) -> str:
    from inference_service.main import get_settings

    settings = get_settings()
    expected = settings.inference_secret
    if not expected:
        if settings.allow_insecure_dev:
            logger.warning(
                "INFERENCE_SERVICE_SECRET not set — classify endpoint UNPROTECTED (dev mode)"
            )
            return ""
        raise InferenceUnavailableError("inference service not configured")
    if not x_inference_secret or not hmac.compare_digest(
        x_inference_secret.encode("utf-8"), expected.encode("utf-8")
    ):
        raise InferenceAuthError("forbidden")
    return x_inference_secret
