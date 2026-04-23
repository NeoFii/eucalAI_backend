"""ConfigManager: 3-tier config source (admin → cached_previous → local_fallback)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from router_service.gateway_admin import AdminConfigGateway
from router_service.utils.runtime_config import (
    RuntimeConfigStore,
    normalize_runtime_config,
)

_logger = logging.getLogger("router_service")


class ConfigManager:
    """Manage routing configuration with admin-service as primary source."""

    def __init__(
        self,
        settings: Any,
        runtime_config_path: str,
    ) -> None:
        self._settings = settings
        self._local_store = RuntimeConfigStore(runtime_config_path)
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

    async def start(self) -> None:
        admin_config = None
        try:
            admin_config = await AdminConfigGateway.fetch_active_config(self._settings)
        except Exception:
            _logger.warning("failed to fetch config from admin-service", exc_info=True)

        if admin_config is not None:
            try:
                self._cached_config = normalize_runtime_config(admin_config)
                self._config_version = admin_config.get("version")
                self._config_source = "admin"
                self._last_updated_at = datetime.now(timezone.utc)
                _logger.info(
                    "loaded routing config from admin-service v%s", self._config_version
                )
            except Exception:
                _logger.warning("admin config normalization failed, trying local fallback", exc_info=True)
                admin_config = None

        if admin_config is None:
            try:
                local = self._local_store.load()
                if not local.get("model_providers"):
                    raise RuntimeError(
                        "local runtime_config.json has no model_providers — "
                        "router-service cannot start without provider configuration"
                    )
                self._cached_config = local
                self._config_version = None
                self._config_source = "local_fallback"
                self._last_updated_at = datetime.now(timezone.utc)
                _logger.info("loaded routing config from local fallback")
            except RuntimeError:
                raise
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
            raise RuntimeError("ConfigManager not started")
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
                new_config = normalize_runtime_config(resp)
                new_version = resp.get("version")
                if new_version != self._config_version:
                    _logger.info(
                        "config updated: v%s → v%s", self._config_version, new_version
                    )
                self._cached_config = new_config
                self._config_version = new_version
                self._config_source = "admin"
                self._last_updated_at = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._config_source == "admin":
                    self._config_source = "cached_previous"
                _logger.warning("config refresh failed, keeping current config", exc_info=True)
