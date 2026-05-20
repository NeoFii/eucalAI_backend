"""ConfigManager: admin-service config with cached_previous fallback."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.common.internal import InternalServiceResponseError
from app.common.observability import log_event
from app.core.exceptions import InferenceConfigError
from app.gateway.api_service_config import ApiServiceConfigGateway
from app.utils.runtime_config import normalize_inference_config

_logger = logging.getLogger("inference_service")


class ConfigManager:
    """Manage routing configuration with admin-service as sole source."""

    def __init__(
        self,
        *,
        gateway: ApiServiceConfigGateway,
        refresh_interval_seconds: int = 60,
    ) -> None:
        self._gateway = gateway
        self._refresh_interval = refresh_interval_seconds
        self._cached_config: Dict[str, Any] | None = None
        self._config_version: int | None = None
        self._config_source: str = "none"
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
        try:
            admin_config = await self._gateway.fetch_active_config()
        except InternalServiceResponseError as exc:
            if exc.status_code in (401, 403):
                raise RuntimeError(
                    f"admin-service rejected credentials (HTTP {exc.status_code}): {exc.detail}"
                ) from exc
            raise RuntimeError(
                f"failed to fetch routing config from admin-service (HTTP {exc.status_code})"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                "failed to fetch routing config from admin-service"
            ) from exc

        if admin_config is None:
            raise RuntimeError(
                "admin-service returned no active routing config"
            )

        self._cached_config = normalize_inference_config(admin_config)
        self._config_version = admin_config.get("version")
        self._config_source = "admin"
        self._last_updated_at = datetime.now(timezone.utc)
        log_event(
            _logger, logging.INFO, "configLoadedFromAdmin",
            version=self._config_version,
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
        while True:
            await asyncio.sleep(self._refresh_interval)
            try:
                resp = await self._gateway.fetch_active_config()
                if resp is None:
                    if self._config_source == "admin":
                        self._config_source = "cached_previous"
                        _logger.warning("admin config unavailable, using cached_previous")
                    continue
                new_config = normalize_inference_config(resp)
                new_version = resp.get("version")
                if new_version != self._config_version:
                    log_event(
                        _logger, logging.INFO, "configUpdated",
                        oldVersion=self._config_version,
                        newVersion=new_version,
                    )
                self._cached_config = new_config
                self._config_version = new_version
                self._config_source = "admin"
                self._last_updated_at = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                raise
            except InternalServiceResponseError as exc:
                if exc.status_code in (401, 403):
                    _logger.error(
                        "admin credentials rejected (HTTP %s), using cached config",
                        exc.status_code,
                    )
                else:
                    _logger.warning(
                        "config refresh failed (HTTP %s), keeping current config",
                        exc.status_code,
                        exc_info=True,
                    )
                if self._config_source == "admin":
                    self._config_source = "cached_previous"
            except Exception:
                if self._config_source == "admin":
                    self._config_source = "cached_previous"
                _logger.warning("config refresh failed, keeping current config", exc_info=True)
