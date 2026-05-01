"""Router-service configuration: constants and pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, List

from pydantic import model_validator

from common.config import BaseServiceSettings

# ---------------------------------------------------------------------------
# Five-way route order (needed by RuntimeConfigStore for validation)
# ---------------------------------------------------------------------------
FIVEWAY_ROUTE_ORDER: List[str] = ["纠错", "工具调用", "通用任务", "任务拆解", "编程"]
FIVEWAY_DEFAULT_WEIGHTS: Dict[str, float] = {
    "纠错": 1.0,
    "工具调用": 1.0,
    "通用任务": 1.0,
    "任务拆解": 1.0,
    "编程": 1.0,
}

DEFAULT_ROUTER_ALIAS = "auto"


# ---------------------------------------------------------------------------
# Service settings (pydantic-settings, extends BaseServiceSettings)
# ---------------------------------------------------------------------------
class RouterSettings(BaseServiceSettings):
    """Router-service specific settings."""

    SERVICE_NAME: str = "router-service"
    PORT: int = 8003

    USER_SERVICE_URL: str = "http://127.0.0.1:8000"
    INFERENCE_SERVICE_URL: str = "http://127.0.0.1:8004"
    INFERENCE_SERVICE_SECRET: str = ""
    ADMIN_SERVICE_URL: str = "http://127.0.0.1:8001"

    CONFIG_REFRESH_INTERVAL_SECONDS: int = 60
    CONFIG_FETCH_TIMEOUT_SECONDS: float = 5.0

    CHANNEL_MAX_RETRIES: int = 2
    CHANNEL_COOLDOWN_SECONDS: float = 30.0
    CHANNEL_AUTO_DISABLE_ENABLED: bool = True
    CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD: int = 5
    CHANNEL_AUTO_DISABLE_COOLDOWN_SECONDS: float = 300.0
    CHANNEL_HEALTH_REDIS_URL: str = ""

    ROUTER_REDIS_URL: str = ""

    CALLLOG_FLUSH_INTERVAL: float = 5.0
    CALLLOG_MAX_BUFFER: int = 10000
    CALLLOG_MAX_RETRIES: int = 3

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_USER_RPM: int = 20
    RATE_LIMIT_GLOBAL_RPM: int = 0

    CHANNEL_AFFINITY_ENABLED: bool = False
    CHANNEL_AFFINITY_TTL: int = 3600
    CHANNEL_AFFINITY_LRU_MAXSIZE: int = 10000

    ROUTER_RUNTIME_CONFIG: str = ""

    # Override base class validator: router-service has no DB/JWT
    @model_validator(mode="after")
    def validate_required_fields(self) -> "RouterSettings":
        if not self.INTERNAL_SECRET:
            raise ValueError("INTERNAL_SECRET must be configured")
        if len(self.INTERNAL_SECRET) < 32:
            raise ValueError("INTERNAL_SECRET length must be at least 32")
        return self


@lru_cache
def get_settings() -> RouterSettings:
    return RouterSettings()
