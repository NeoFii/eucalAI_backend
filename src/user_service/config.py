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
    ROUTER_SERVICE_URL: str = "http://localhost:8003"

    EMAIL_CODE_EXPIRE_MINUTES: int = 5

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
