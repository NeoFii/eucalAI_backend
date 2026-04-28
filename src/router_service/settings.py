"""Lightweight settings for router-service (CPU gateway).

Does not inherit BaseServiceSettings — router-service stays independent
of the common config layer by design.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from common.observability import parse_bool_env


@dataclass(slots=True)
class RouterSettings:
    user_service_url: str = "http://127.0.0.1:8000"
    internal_secret: str = ""
    inference_service_url: str = "http://127.0.0.1:8004"
    inference_service_secret: str = ""
    internal_http_max_retries: int = 1
    internal_http_retry_backoff_seconds: float = 0.2
    internal_http_circuit_breaker_threshold: int = 3
    internal_http_circuit_breaker_cooldown_seconds: float = 30.0
    admin_service_url: str = "http://127.0.0.1:8001"
    config_refresh_interval_seconds: int = 60
    config_fetch_timeout_seconds: float = 5.0
    log_level: str = "INFO"
    log_dir: str = "logs"
    env: str = "development"
    log_to_file: bool = False
    log_file_max_bytes: int = 50 * 1024 * 1024
    log_file_backup_count: int = 5
    channel_max_retries: int = 2
    channel_cooldown_seconds: float = 30.0
    channel_auto_disable_enabled: bool = True
    channel_auto_disable_failure_threshold: int = 5
    channel_auto_disable_cooldown_seconds: float = 300.0
    channel_health_redis_url: str = ""

    @classmethod
    def from_env(cls) -> "RouterSettings":
        return cls(
            user_service_url=os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8000"),
            internal_secret=os.getenv("INTERNAL_SECRET", ""),
            inference_service_url=os.getenv("INFERENCE_SERVICE_URL", "http://127.0.0.1:8004"),
            inference_service_secret=os.getenv("INFERENCE_SERVICE_SECRET", ""),
            internal_http_max_retries=int(os.getenv("INTERNAL_HTTP_MAX_RETRIES", "1")),
            internal_http_retry_backoff_seconds=float(
                os.getenv("INTERNAL_HTTP_RETRY_BACKOFF_SECONDS", "0.2")
            ),
            internal_http_circuit_breaker_threshold=int(
                os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD", "3")
            ),
            internal_http_circuit_breaker_cooldown_seconds=float(
                os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "30.0")
            ),
            admin_service_url=os.getenv("ADMIN_SERVICE_URL", "http://127.0.0.1:8001"),
            config_refresh_interval_seconds=int(os.getenv("CONFIG_REFRESH_INTERVAL_SECONDS", "60")),
            config_fetch_timeout_seconds=float(os.getenv("CONFIG_FETCH_TIMEOUT_SECONDS", "5.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=os.getenv("ROUTER_LOG_DIR", os.getenv("LOG_DIR", "logs")),
            env=os.getenv("ENV", "development"),
            log_to_file=parse_bool_env(os.getenv("LOG_TO_FILE"), default=False),
            log_file_max_bytes=int(os.getenv("LOG_FILE_MAX_BYTES", str(50 * 1024 * 1024))),
            log_file_backup_count=int(os.getenv("LOG_FILE_BACKUP_COUNT", "5")),
            channel_max_retries=int(os.getenv("CHANNEL_MAX_RETRIES", "2")),
            channel_cooldown_seconds=float(os.getenv("CHANNEL_COOLDOWN_SECONDS", "30.0")),
            channel_auto_disable_enabled=parse_bool_env(
                os.getenv("CHANNEL_AUTO_DISABLE_ENABLED"), default=True,
            ),
            channel_auto_disable_failure_threshold=int(
                os.getenv("CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD", "5")
            ),
            channel_auto_disable_cooldown_seconds=float(
                os.getenv("CHANNEL_AUTO_DISABLE_COOLDOWN_SECONDS", "300.0")
            ),
            channel_health_redis_url=os.getenv("CHANNEL_HEALTH_REDIS_URL", ""),
        )
