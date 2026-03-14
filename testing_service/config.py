# -*- coding: utf-8 -*-
"""Testing service settings."""

from functools import lru_cache

from pydantic import AliasChoices, Field

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Testing-service configuration."""

    PROJECT_NAME: str = "Eucal AI Testing Service"
    SERVICE_NAME: str = "testing-service"
    DESCRIPTION: str = "Model management, provider management and benchmark APIs"
    PORT: int = 8002
    DATABASE_URL: str = Field(
        default="mysql+aiomysql://root:password@localhost:3306/eucal_ai_testing",
        validation_alias=AliasChoices("TESTING_DATABASE_URL"),
    )
    ADMIN_SERVICE_URL: str = Field(
        default="http://127.0.0.1:8001",
        validation_alias=AliasChoices("ADMIN_SERVICE_URL", "TESTING_ADMIN_SERVICE_URL"),
    )

    SNOWFLAKE_WORKER_ID: int = 3
    LOG_FILE_PREFIX: str = "testing"

    BENCHMARK_DEFAULT_TIMEOUT: int = 60
    BENCHMARK_DEFAULT_CONCURRENCY: int = 10
    BENCHMARK_DEFAULT_RATE_LIMIT: int = 60

    CACHE_TTL_SHORT: int = 300
    CACHE_TTL_LONG: int = 86400

    TESTING_SECRET_MASTER_KEY: str = ""

    PROBE_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices("PROBE_ENABLED", "TESTING_PROBE_ENABLED"),
    )
    PROBE_SCHEDULER_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "PROBE_SCHEDULER_ENABLED",
            "TESTING_PROBE_SCHEDULER_ENABLED",
        ),
    )
    PROBE_CRON_HOURS: str = Field(
        default="0,6,12,18",
        validation_alias=AliasChoices("PROBE_CRON_HOURS", "TESTING_PROBE_CRON_HOURS"),
    )
    PROBE_REGION: str = Field(
        default="cn-east",
        validation_alias=AliasChoices("PROBE_REGION", "TESTING_PROBE_REGION"),
    )
    BENCHMARK_QUEUE_REDIS_URL: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices(
            "BENCHMARK_QUEUE_REDIS_URL",
            "TESTING_BENCHMARK_QUEUE_REDIS_URL",
        ),
    )
    BENCHMARK_WORKER_CONCURRENCY: int = Field(
        default=10,
        validation_alias=AliasChoices(
            "BENCHMARK_WORKER_CONCURRENCY",
            "TESTING_BENCHMARK_WORKER_CONCURRENCY",
        ),
    )
    BENCHMARK_JOB_TIMEOUT_SECONDS: int = Field(
        default=300,
        validation_alias=AliasChoices(
            "BENCHMARK_JOB_TIMEOUT_SECONDS",
            "TESTING_BENCHMARK_JOB_TIMEOUT_SECONDS",
        ),
    )
    BENCHMARK_QUEUE_CONNECT_TIMEOUT_SECONDS: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "BENCHMARK_QUEUE_CONNECT_TIMEOUT_SECONDS",
            "TESTING_BENCHMARK_QUEUE_CONNECT_TIMEOUT_SECONDS",
        ),
    )
    BENCHMARK_QUEUE_CONNECT_RETRIES: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "BENCHMARK_QUEUE_CONNECT_RETRIES",
            "TESTING_BENCHMARK_QUEUE_CONNECT_RETRIES",
        ),
    )
    BENCHMARK_QUEUE_CONNECT_RETRY_DELAY_SECONDS: float = Field(
        default=0.2,
        validation_alias=AliasChoices(
            "BENCHMARK_QUEUE_CONNECT_RETRY_DELAY_SECONDS",
            "TESTING_BENCHMARK_QUEUE_CONNECT_RETRY_DELAY_SECONDS",
        ),
    )
    BENCHMARK_MAX_ENQUEUED_JOBS: int = Field(
        default=500,
        validation_alias=AliasChoices(
            "BENCHMARK_MAX_ENQUEUED_JOBS",
            "TESTING_BENCHMARK_MAX_ENQUEUED_JOBS",
        ),
    )
    BENCHMARK_ENABLE_SCHEDULER_ENQUEUE: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "BENCHMARK_ENABLE_SCHEDULER_ENQUEUE",
            "TESTING_BENCHMARK_ENABLE_SCHEDULER_ENQUEUE",
        ),
    )

    HOST: str = "0.0.0.0"

    @property
    def host(self) -> str:
        return self.HOST

    @property
    def port(self) -> int:
        return self.PORT

    @property
    def jwt_secret_key(self) -> str:
        return self.JWT_SECRET_KEY

    @property
    def jwt_algorithm(self) -> str:
        return self.JWT_ALGORITHM

    @property
    def internal_secret(self) -> str:
        return self.INTERNAL_SECRET

    @property
    def admin_service_url(self) -> str:
        return self.ADMIN_SERVICE_URL

    @property
    def benchmark_default_timeout(self) -> int:
        return self.BENCHMARK_DEFAULT_TIMEOUT

    @property
    def benchmark_default_concurrency(self) -> int:
        return self.BENCHMARK_DEFAULT_CONCURRENCY

    @property
    def benchmark_default_rate_limit(self) -> int:
        return self.BENCHMARK_DEFAULT_RATE_LIMIT

    @property
    def cache_ttl_short(self) -> int:
        return self.CACHE_TTL_SHORT

    @property
    def cache_ttl_long(self) -> int:
        return self.CACHE_TTL_LONG

    @property
    def testing_secret_master_key(self) -> str:
        return self.TESTING_SECRET_MASTER_KEY

    @property
    def probe_enabled(self) -> bool:
        return self.PROBE_ENABLED

    @property
    def probe_scheduler_enabled(self) -> bool:
        return self.PROBE_SCHEDULER_ENABLED

    @property
    def probe_cron_hours(self) -> str:
        return self.PROBE_CRON_HOURS

    @property
    def probe_region(self) -> str:
        return self.PROBE_REGION

    @property
    def benchmark_queue_redis_url(self) -> str:
        return self.BENCHMARK_QUEUE_REDIS_URL

    @property
    def benchmark_worker_concurrency(self) -> int:
        return self.BENCHMARK_WORKER_CONCURRENCY

    @property
    def benchmark_job_timeout_seconds(self) -> int:
        return self.BENCHMARK_JOB_TIMEOUT_SECONDS

    @property
    def benchmark_queue_connect_timeout_seconds(self) -> int:
        return self.BENCHMARK_QUEUE_CONNECT_TIMEOUT_SECONDS

    @property
    def benchmark_queue_connect_retries(self) -> int:
        return self.BENCHMARK_QUEUE_CONNECT_RETRIES

    @property
    def benchmark_queue_connect_retry_delay_seconds(self) -> float:
        return self.BENCHMARK_QUEUE_CONNECT_RETRY_DELAY_SECONDS

    @property
    def benchmark_max_enqueued_jobs(self) -> int:
        return self.BENCHMARK_MAX_ENQUEUED_JOBS

    @property
    def benchmark_enable_scheduler_enqueue(self) -> bool:
        return self.BENCHMARK_ENABLE_SCHEDULER_ENQUEUE

    @property
    def auto_init_db(self) -> bool:
        return self.AUTO_INIT_DB

@lru_cache
def get_settings() -> Settings:
    """Return cached testing settings."""
    return Settings()
