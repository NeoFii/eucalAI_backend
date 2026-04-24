"""Lightweight settings for router-service (CPU gateway).

Does not inherit BaseServiceSettings — router-service stays independent
of the common config layer by design.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


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

    @classmethod
    def from_env(cls) -> "RouterSettings":
        return cls(
            user_service_url=os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8000"),
            internal_secret=os.getenv("INTERNAL_SECRET", ""),
            inference_service_url=os.getenv(
                "INFERENCE_SERVICE_URL", "http://127.0.0.1:8004"
            ),
            inference_service_secret=os.getenv("INFERENCE_SERVICE_SECRET", ""),
            internal_http_max_retries=int(
                os.getenv("INTERNAL_HTTP_MAX_RETRIES", "1")
            ),
            internal_http_retry_backoff_seconds=float(
                os.getenv("INTERNAL_HTTP_RETRY_BACKOFF_SECONDS", "0.2")
            ),
            internal_http_circuit_breaker_threshold=int(
                os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD", "3")
            ),
            internal_http_circuit_breaker_cooldown_seconds=float(
                os.getenv("INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "30.0")
            ),
            admin_service_url=os.getenv(
                "ADMIN_SERVICE_URL", "http://127.0.0.1:8001"
            ),
            config_refresh_interval_seconds=int(
                os.getenv("CONFIG_REFRESH_INTERVAL_SECONDS", "60")
            ),
            config_fetch_timeout_seconds=float(
                os.getenv("CONFIG_FETCH_TIMEOUT_SECONDS", "5.0")
            ),
        )
