"""ConfigManager: 3-tier config source (admin → cached_previous → local_fallback)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from common.internal import InternalServiceResponseError
from common.observability import log_event
from inference_service.gateway import AdminConfigGateway
from inference_service.schemas.errors import InferenceConfigError
from inference_service.utils.runtime_config import normalize_inference_config

_logger = logging.getLogger("inference_service")


class ConfigManager:
    """Manage routing configuration with admin-service as primary source."""

    def __init__(
        self,
        settings: Any,
        runtime_config_path: str,
    ) -> None:
        self._settings = settings
        self._runtime_config_path = runtime_config_path
        self._cached_config: Dict[str, Any] | None = None
        self._config_version: int | None = None
        self._config_source: str = "local_fallback"
        self._last_updated_at: datetime | None = None
        self._refresh_task: asyncio.Task | None = None

    @property
    def config_version(self) -> int | None:
        return self._config_version

    @property
    def config_source(self) -> str:
        return self._config_source

    @property
    def last_updated_at(self) -> datetime | None:
        return self._last_updated_at

    def _load_local_fallback(self) -> Dict[str, Any]:
        """Load and normalize local config, stripping model_providers."""
        import os
        path = self._runtime_config_path
        if not path or not os.path.exists(path):
            raise RuntimeError(f"local runtime config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return normalize_inference_config(raw)

    async def start(self) -> None:
        admin_config = None
        try:
            admin_config = await AdminConfigGateway.fetch_active_config(self._settings)
        except InternalServiceResponseError as exc:
            if exc.status_code in (401, 403):
                raise RuntimeError(
                    f"admin-service rejected credentials (HTTP {exc.status_code}): {exc.detail}"
                ) from exc
            _logger.warning("admin-service returned error, trying local fallback", exc_info=True)
        except Exception:
            _logger.warning("failed to fetch config from admin-service", exc_info=True)

        if admin_config is not None:
            try:
                padded = {**admin_config, "model_providers": {}, "router_alias": admin_config.get("router_alias", "auto")}
                self._cached_config = normalize_inference_config(padded)
                self._config_version = admin_config.get("version")
                self._config_source = "admin"
                self._last_updated_at = datetime.now(timezone.utc)
                log_event(_logger, logging.INFO, "configLoadedFromAdmin", version=self._config_version)
            except Exception:
                _logger.warning("admin config normalization failed, trying local fallback", exc_info=True)
                admin_config = None

        if admin_config is None:
            try:
                local = self._load_local_fallback()
                self._cached_config = local
                self._config_version = None
                self._config_source = "local_fallback"
                self._last_updated_at = datetime.now(timezone.utc)
                log_event(_logger, logging.INFO, "configLoadedFromLocal")
            except Exception:
                raise RuntimeError(
                    "failed to load routing config from both admin-service and local file"
                )

        self._refresh_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
            self._refresh_task = None

    def load(self) -> Dict[str, Any]:
        if self._cached_config is None:
            raise InferenceConfigError("config not loaded — ConfigManager not started")
        return self._cached_config

    async def _poll_loop(self) -> None:
        interval = self._settings.config_refresh_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                resp = await AdminConfigGateway.fetch_active_config(self._settings)
                if resp is None:
                    if self._config_source == "admin":
                        self._config_source = "cached_previous"
                        _logger.warning("admin config unavailable, using cached_previous")
                    continue
                padded = {**resp, "model_providers": {}, "router_alias": resp.get("router_alias", "auto")}
                new_config = normalize_inference_config(padded)
                new_version = resp.get("version")
                if new_version != self._config_version:
                    log_event(_logger, logging.INFO, "configUpdated", oldVersion=self._config_version, newVersion=new_version)
                self._cached_config = new_config
                self._config_version = new_version
                self._config_source = "admin"
                self._last_updated_at = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                raise
            except InternalServiceResponseError as exc:
                if exc.status_code in (401, 403):
                    _logger.error("admin credentials rejected (HTTP %s), using cached config", exc.status_code)
                else:
                    _logger.warning("config refresh failed (HTTP %s), keeping current config", exc.status_code, exc_info=True)
                if self._config_source == "admin":
                    self._config_source = "cached_previous"
            except Exception:
                if self._config_source == "admin":
                    self._config_source = "cached_previous"
                _logger.warning("config refresh failed, keeping current config", exc_info=True)
