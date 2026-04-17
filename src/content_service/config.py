"""Content service settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Union

from pydantic import AliasChoices, Field

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Content service configuration."""

    PROJECT_NAME: str = "Eucal AI Content Service"
    SERVICE_NAME: str = "content-service"
    DESCRIPTION: str = "Content and news management service"
    PORT: int = 8004
    DATABASE_URL: str = Field(
        default="mysql+aiomysql://root:password@localhost:3306/eucal_ai_content",
        validation_alias=AliasChoices("CONTENT_DATABASE_URL"),
    )
    SNOWFLAKE_WORKER_ID: int = 5
    LOG_FILE_PREFIX: str = "content"
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    ADMIN_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        validation_alias=AliasChoices("CONTENT_ADMIN_SERVICE_URL", "ADMIN_SERVICE_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()


settings = get_settings()
