"""Admin service settings."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional, Union
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, model_validator

from common.config import BaseServiceSettings
from common.utils.crypto import validate_master_key

_config_logger = logging.getLogger(__name__)


class Settings(BaseServiceSettings):
    """Admin service settings."""

    PROJECT_NAME: str = "Eucal AI Admin Service"
    SERVICE_NAME: str = "admin-service"
    DESCRIPTION: str = "Eucal AI Admin Service API"

    PORT: int = 8001
    DATABASE_URL: str = Field(
        default="mysql+aiomysql://root:password@localhost:3306/eucal_ai_admin",
        validation_alias=AliasChoices("ADMIN_DATABASE_URL"),
    )
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    INTERNAL_API_PREFIX: str = "/internal"
    USER_SERVICE_URL: str = "http://127.0.0.1:8000"
    ROUTER_SERVICE_URL: str = "http://127.0.0.1:8003"
    INFERENCE_SERVICE_URL: str = "http://127.0.0.1:8004"

    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    @model_validator(mode="after")
    def _check_config_consistency(self) -> Settings:
        parsed = urlparse(self.USER_SERVICE_URL)
        user_port = parsed.port or 80
        if user_port == self.PORT:
            _config_logger.warning(
                "USER_SERVICE_URL (%s) points to the same port as this service (%d). "
                "Admin-to-user gateway calls may loop back; check USER_SERVICE_URL.",
                self.USER_SERVICE_URL,
                self.PORT,
            )
        if not self.DEBUG:
            if not self.COOKIE_SECURE:
                _config_logger.warning(
                    "Forcing COOKIE_SECURE=True because DEBUG is False"
                )
                self.COOKIE_SECURE = True
            if self.COOKIE_SAMESITE != "strict":
                _config_logger.warning(
                    "Forcing COOKIE_SAMESITE='strict' because DEBUG is False"
                )
                self.COOKIE_SAMESITE = "strict"
        return self

    SNOWFLAKE_WORKER_ID: int = 2
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ADMIN_TOKEN_EXPIRE_MINUTES: int = 480

    BOOTSTRAP_SUPERADMIN_ENABLED: bool = False
    BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP: bool = True
    BOOTSTRAP_SUPERADMIN_EMAIL: Optional[str] = None
    BOOTSTRAP_SUPERADMIN_PASSWORD: Optional[str] = None
    BOOTSTRAP_SUPERADMIN_NAME: Optional[str] = None
    BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS: bool = False
    BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS: bool = False

    PROVIDER_SECRET_MASTER_KEY: str = ""

    ADMIN_QUEUE_REDIS_URL: str = "redis://127.0.0.1:6379/3"
    ADMIN_WORKER_CONCURRENCY: int = 3
    ADMIN_JOB_TIMEOUT_SECONDS: int = 600
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 15.0
    HEALTH_CHECK_LLM_PROBE_ENABLED: bool = True
    HEALTH_CHECK_LLM_PROBE_MAX_TOKENS: int = 5
    HEALTH_CHECK_RATE_LIMIT_DELAY: float = 0.5

    LOG_FILE_PREFIX: str = "admin"

    @model_validator(mode="after")
    def _validate_provider_master_key(self) -> Settings:
        if not self.PROVIDER_SECRET_MASTER_KEY:
            raise ValueError("PROVIDER_SECRET_MASTER_KEY must be configured")
        validate_master_key(self.PROVIDER_SECRET_MASTER_KEY)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached admin settings."""
    return Settings()


settings = get_settings()
