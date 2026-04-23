"""Lightweight shared-secret authentication for inference-service."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException

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
        raise HTTPException(status_code=503, detail="inference service not configured")
    if not x_inference_secret or not hmac.compare_digest(
        x_inference_secret.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="forbidden")
    return x_inference_secret
