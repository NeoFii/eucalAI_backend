"""Unified api-service settings — merges user-service, admin-service, router-service configs."""

from __future__ import annotations

from functools import lru_cache

from api_service.common.config import BaseServiceSettings


class ApiServiceSettings(BaseServiceSettings):
    """Unified settings for the merged api-service."""

    # ── Base ──────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Eucal AI API Service"
    SERVICE_NAME: str = "api-service"
    DESCRIPTION: str = "Eucal AI Unified API Service"
    PORT: int = 8000

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    CACHE_REDIS_URL: str = "redis://127.0.0.1:6379/2"
    WORKER_QUEUE_REDIS_URL: str = "redis://127.0.0.1:6379/1"

    # ── Inference Service ─────────────────────────────────────────────────
    INFERENCE_SERVICE_URL: str = "http://127.0.0.1:8004"
    INFERENCE_SERVICE_SECRET: str = ""

    # ── Admin ─────────────────────────────────────────────────────────────
    BOOTSTRAP_SUPERADMIN_ENABLED: bool = False
    BOOTSTRAP_SUPERADMIN_EMAIL: str | None = None
    BOOTSTRAP_SUPERADMIN_PASSWORD: str | None = None
    BOOTSTRAP_SUPERADMIN_NAME: str | None = None
    PROVIDER_SECRET_MASTER_KEY: str = ""
    ADMIN_TOKEN_EXPIRE_MINUTES: int = 480

    # ── User ──────────────────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM: str = "Eucal AI"
    MAX_API_KEYS_PER_USER: int = 20
    LOGIN_MAX_FAILURES: int = 5
    EMAIL_CODE_EXPIRE_MINUTES: int = 5

    # ── Relay ─────────────────────────────────────────────────────────────
    CHANNEL_MAX_RETRIES: int = 2
    CHANNEL_COOLDOWN_SECONDS: float = 30.0
    CHANNEL_AUTO_DISABLE_ENABLED: bool = True
    CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD: int = 5
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_USER_RPM: int = 20
    RATE_LIMIT_GLOBAL_RPM: int = 0
    SDK_CLIENT_POOL_MAX_SIZE: int = 64
    ANTHROPIC_NATIVE_SLUGS: list[str] = ["anthropic"]
    CHANNEL_AFFINITY_ENABLED: bool = False
    CHANNEL_AFFINITY_TTL: int = 3600

    # ── CORS ──────────────────────────────────────────────────────────────
    ALLOWED_HOSTS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_FILE_PREFIX: str = "api"

    # ── Snowflake ─────────────────────────────────────────────────────────
    SNOWFLAKE_WORKER_ID: int = 1


@lru_cache
def get_settings() -> ApiServiceSettings:
    return ApiServiceSettings()


settings = get_settings()
