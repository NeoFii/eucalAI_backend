"""Lightweight shared-secret authentication for inference-service."""

from __future__ import annotations

from fastapi import Header, HTTPException


def require_inference_secret(
    x_inference_secret: str | None = Header(default=None),
) -> str:
    from inference_service.main import get_settings

    settings = get_settings()
    expected = settings.inference_secret
    if not expected:
        return ""
    if not x_inference_secret or x_inference_secret != expected:
        raise HTTPException(status_code=403, detail="forbidden")
    return x_inference_secret
