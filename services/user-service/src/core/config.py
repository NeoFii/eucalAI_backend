"""User service settings."""

from functools import lru_cache

from pydantic import AliasChoices, Field

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """User service settings."""

    PROJECT_NAME: str = "Eucal AI User Service"
    SERVICE_NAME: str = "user-service"
    DESCRIPTION: str = "Eucal AI User Service API"
    PORT: int = 8000
    DATABASE_URL: str = Field(
        default="mysql+aiomysql://root:password@localhost:3306/eucal_ai_user",
        validation_alias=AliasChoices("USER_DATABASE_URL"),
    )
    SNOWFLAKE_WORKER_ID: int = 1
    LOG_FILE_PREFIX: str = "user"

    ADMIN_SERVICE_URL: str = "http://localhost:8001"
    CACHE_REDIS_URL: str = "redis://127.0.0.1:6379/2"

    EMAIL_CODE_EXPIRE_MINUTES: int = 5
    MIN_TOPUP_AMOUNT: int = 1_000_000
    MAX_TOPUP_AMOUNT: int = 10_000_000_000
    MAX_API_KEYS_PER_USER: int = 20
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCK_DURATION_HOURS: int = 1
    MAX_CODE_ERRORS: int = 5
    CODE_ERROR_LOCK_HOURS: int = 24
    CODE_DAILY_SEND_LIMIT: int = 3
    USER_QUEUE_REDIS_URL: str = "redis://127.0.0.1:6379/1"
    USER_WORKER_CONCURRENCY: int = 5
    USER_JOB_TIMEOUT_SECONDS: int = 300
    VERIFICATION_CODE_RETENTION_DAYS: int = 7

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM: str = "Eucal AI"


@lru_cache
def get_settings() -> Settings:
    """Return cached user settings."""
    return Settings()


settings = get_settings()
