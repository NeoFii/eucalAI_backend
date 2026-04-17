"""Router service settings."""

from __future__ import annotations

import os
import hashlib
from functools import lru_cache
from typing import Dict

from pydantic import AliasChoices, Field, field_validator

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Router service configuration."""

    PROJECT_NAME: str = "Eucal AI Router Service"
    SERVICE_NAME: str = "router-service"
    DESCRIPTION: str = "OpenAI-compatible router and billing service"
    PORT: int = 8003
    DATABASE_URL: str = Field(
        default="mysql+aiomysql://root:password@localhost:3306/eucal_ai_router",
        validation_alias=AliasChoices("ROUTER_DATABASE_URL"),
    )
    SNOWFLAKE_WORKER_ID: int = 4
    LOG_FILE_PREFIX: str = "router"
    USER_SERVICE_URL: str = "http://localhost:8001"
    TESTING_SERVICE_URL: str = "http://localhost:8001"

    ROUTER_KEY_PREFIX: str = "sk-eucal-"
    ROUTER_SECRET_MASTER_KEY: str = ""
    PROVIDER_SECRET_MASTER_KEY: str = ""
    ROUTER_BILLING_CURRENCY: str = "CNY"
    ROUTER_DEFAULT_BILLING_MODE: str = "postpaid"
    ROUTER_STREAM_TIMEOUT_SECONDS: int = 60
    ROUTER_PENDING_RESERVATION_MAX_AGE_SECONDS: int = 300
    ROUTER_PENDING_RESERVATION_SWEEP_INTERVAL_SECONDS: int = 60

    SMART_ROUTER_ENABLED: bool = False
    SMART_ROUTER_ALIAS: str = "smart-router"
    SMART_ROUTER_CLASSIFIER_MODEL: str = ""
    SMART_ROUTER_CLASSIFIER_TEMPERATURE: float = 0.0
    SMART_ROUTER_CLASSIFIER_TIMEOUT_SECONDS: int = 20
    SMART_ROUTER_CLASSIFIER_MAX_TOKENS: int = 120
    SMART_ROUTER_DIFFICULTY_MODEL_MAP: str = ""
    SMART_ROUTER_FALLBACK_MODEL: str = ""

    @field_validator("ROUTER_DEFAULT_BILLING_MODE")
    @classmethod
    def validate_billing_mode(cls, value: str) -> str:
        normalized = (value or "postpaid").strip().lower()
        if normalized not in {"prepaid", "postpaid"}:
            raise ValueError("ROUTER_DEFAULT_BILLING_MODE must be prepaid or postpaid")
        return normalized

    @field_validator("SMART_ROUTER_ALIAS")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        alias = value.strip()
        if not alias:
            raise ValueError("SMART_ROUTER_ALIAS must not be empty")
        return alias

    @property
    def smart_router_difficulty_model_map(self) -> Dict[int, str]:
        raw = self.SMART_ROUTER_DIFFICULTY_MODEL_MAP.strip()
        if not raw:
            return {}

        parsed: Dict[int, str] = {}
        for item in raw.split(","):
            left, _, right = item.partition(":")
            if not left or not right:
                continue
            try:
                difficulty = int(left.strip())
            except ValueError:
                continue
            target = right.strip()
            if 1 <= difficulty <= 5 and target:
                parsed[difficulty] = target
        return parsed

    @property
    def router_secret_master_key(self) -> str:
        secret = self.ROUTER_SECRET_MASTER_KEY.strip()
        if secret:
            return secret
        return hashlib.sha256(self.JWT_SECRET_KEY.encode("utf-8")).hexdigest()

    @property
    def provider_secret_master_key(self) -> str:
        secret = self.PROVIDER_SECRET_MASTER_KEY.strip()
        if secret:
            return secret
        legacy = os.getenv("TESTING_SECRET_MASTER_KEY", "").strip()
        if legacy:
            return legacy
        return self.router_secret_master_key


@lru_cache
def get_settings() -> Settings:
    """Return cached router settings."""
    return Settings()


settings = get_settings()
