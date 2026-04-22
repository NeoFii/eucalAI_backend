"""Backend-app combined settings.

Individual sub-service settings (admin_service.config, user_service.config)
are loaded separately and feed their own ``DATABASE_URL``. This module only
declares the process-wide overrides: port, snowflake worker id, log prefix.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field

from common.config import BaseServiceSettings


class BackendAppSettings(BaseServiceSettings):
    """Process-level configuration for the combined backend app."""

    PROJECT_NAME: str = "Eucal AI Backend"
    SERVICE_NAME: str = "backend-app"
    DESCRIPTION: str = "Combined FastAPI process for admin/user domains"
    PORT: int = Field(
        default=8001,
        validation_alias=AliasChoices("BACKEND_APP_PORT", "PORT"),
    )
    SNOWFLAKE_WORKER_ID: int = Field(
        default=1,
        validation_alias=AliasChoices("BACKEND_APP_SNOWFLAKE_WORKER_ID", "SNOWFLAKE_WORKER_ID"),
    )
    LOG_FILE_PREFIX: str = "backend-app"


@lru_cache
def get_settings() -> BackendAppSettings:
    return BackendAppSettings()


settings = get_settings()
