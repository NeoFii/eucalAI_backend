# -*- coding: utf-8 -*-
"""ARQ queue helpers for benchmark jobs."""

from __future__ import annotations

from urllib.parse import urlparse

from arq import create_pool
from arq.connections import RedisSettings

from testing_service.config import get_settings


class BenchmarkQueueUnavailableError(RuntimeError):
    """Raised when Redis/ARQ is not available for benchmark enqueue."""

def build_redis_settings(redis_url: str | None = None):
    settings = get_settings()
    parsed = urlparse(redis_url or get_settings().benchmark_queue_redis_url)
    if not parsed.scheme or not parsed.hostname:
        raise BenchmarkQueueUnavailableError("Invalid benchmark Redis URL")

    database = 0
    path = (parsed.path or "").lstrip("/")
    if path:
        try:
            database = int(path)
        except ValueError as exc:
            raise BenchmarkQueueUnavailableError("Invalid Redis database index") from exc

    return RedisSettings(
        host=parsed.hostname,
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
        conn_timeout=settings.benchmark_queue_connect_timeout_seconds,
        conn_retries=settings.benchmark_queue_connect_retries,
        conn_retry_delay=settings.benchmark_queue_connect_retry_delay_seconds,
    )


async def enqueue_job(function_name: str, *args, _job_id: str | None = None):
    try:
        redis = await create_pool(build_redis_settings())
    except Exception as exc:  # pragma: no cover - network dependent
        raise BenchmarkQueueUnavailableError(str(exc)) from exc
    try:
        job = await redis.enqueue_job(function_name, *args, _job_id=_job_id)
    except Exception as exc:  # pragma: no cover - network dependent
        raise BenchmarkQueueUnavailableError(str(exc)) from exc
    finally:
        await redis.aclose()
    if job is None:
        raise BenchmarkQueueUnavailableError(f"Job enqueue rejected: {function_name}")
    return job
