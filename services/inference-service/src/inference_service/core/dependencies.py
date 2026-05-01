"""FastAPI dependency injection functions for inference-service."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING

from fastapi import Depends, Header

from inference_service.core.config import get_settings
from inference_service.core.exceptions import InferenceAuthError, InferenceUnavailableError

if TYPE_CHECKING:
    from inference_service.core.config import InferenceSettings
    from inference_service.services.config_manager import ConfigManager
    from inference_service.services.router_engine import HybridIntegratedDifficultyRouter

logger = logging.getLogger("inference_service")

_engine: HybridIntegratedDifficultyRouter | None = None
_config_manager: ConfigManager | None = None


def set_engine(engine: HybridIntegratedDifficultyRouter) -> None:
    global _engine
    _engine = engine


def set_config_manager(cm: ConfigManager) -> None:
    global _config_manager
    _config_manager = cm


def get_engine() -> HybridIntegratedDifficultyRouter:
    if _engine is None:
        raise InferenceUnavailableError("router engine not initialized")
    return _engine


def get_config_manager() -> ConfigManager:
    if _config_manager is None:
        raise InferenceUnavailableError("config manager not initialized")
    return _config_manager


def require_inference_secret(
    x_inference_secret: str | None = Header(default=None),
) -> str:
    settings = get_settings()
    expected = settings.INFERENCE_SERVICE_SECRET
    if not expected:
        if settings.INFERENCE_ALLOW_INSECURE_DEV:
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
