"""FastAPI app creation + CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from common.observability import log_event
from router_service.config import DEFAULT_SERVICE_HOST, DEFAULT_SERVICE_PORT
from router_service.dependencies import init_globals
from router_service.logging import get_app_logger, setup_logging
from router_service.routers import chat, completions, meta

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTER_ASSETS = _SERVICE_ROOT / "config"


def _default_asset(name: str, override_env: str) -> str:
    override = os.getenv(override_env)
    if override:
        return override
    return str(_DEFAULT_ROUTER_ASSETS / name)


def create_app(
    runtime_config_path: str | None = None,
    log_dir: str | None = None,
) -> FastAPI:
    from router_service.services.config_manager import ConfigManager
    from router_service.services.inference_client import InferenceClient
    from router_service.services.channel_selector import ChannelSelector
    from router_service.settings import RouterSettings

    settings = RouterSettings.from_env()
    runtime_config_path = runtime_config_path or _default_asset(
        "runtime_config.json", "ROUTER_RUNTIME_CONFIG"
    )
    log_dir = log_dir or settings.log_dir

    setup_logging(
        log_dir=log_dir,
        level=settings.log_level,
        env=settings.env,
        enable_file_logging=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        ring_buffer_capacity=int(os.getenv("LOG_RING_BUFFER_CAPACITY", "2000")),
    )
    logger = get_app_logger()

    inference_client = InferenceClient(
        base_url=settings.inference_service_url,
        secret=settings.inference_service_secret,
        max_retries=settings.internal_http_max_retries,
        retry_backoff=settings.internal_http_retry_backoff_seconds,
        circuit_breaker_threshold=settings.internal_http_circuit_breaker_threshold,
        circuit_breaker_cooldown=settings.internal_http_circuit_breaker_cooldown_seconds,
    )

    config_manager = ConfigManager(
        settings=settings,
        runtime_config_path=runtime_config_path,
    )

    channel_selector = ChannelSelector(
        cooldown_seconds=settings.channel_cooldown_seconds,
        auto_disable_enabled=settings.channel_auto_disable_enabled,
        auto_disable_threshold=settings.channel_auto_disable_failure_threshold,
        auto_disable_cooldown_seconds=settings.channel_auto_disable_cooldown_seconds,
    )

    _health_refresh_task = None
    _redis_conn = None
    _calllog_buffer = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        nonlocal _health_refresh_task, _redis_conn, _calllog_buffer
        log_event(logger, logging.INFO, "serviceStarting", service="router-service")
        await config_manager.start()

        if settings.redis_url:
            import redis.asyncio as aioredis
            try:
                _redis_conn = aioredis.from_url(settings.redis_url, decode_responses=True)
                await _redis_conn.ping()
                log_event(logger, logging.INFO, "redisConnected", url=settings.redis_url)
            except Exception:
                logger.warning("Redis unavailable at %s, features will degrade to in-memory", settings.redis_url)
                _redis_conn = None

        from router_service.services.calllog_buffer import CallLogBuffer
        _calllog_buffer = CallLogBuffer(
            settings=settings,
            flush_interval=settings.calllog_flush_interval,
            max_buffer=settings.calllog_max_buffer,
            max_retries=settings.calllog_max_retries,
        )
        await _calllog_buffer.start()

        rate_limiter = None
        if settings.rate_limit_enabled:
            from router_service.services.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                redis=_redis_conn,
                default_user_rpm=settings.rate_limit_default_user_rpm,
                global_rpm=settings.rate_limit_global_rpm,
            )

        affinity_store = None
        if settings.channel_affinity_enabled:
            from router_service.services.channel_affinity import ChannelAffinityStore
            affinity_store = ChannelAffinityStore(
                redis=_redis_conn,
                ttl=settings.channel_affinity_ttl,
                lru_maxsize=settings.channel_affinity_lru_maxsize,
            )

        init_globals(
            config_manager=config_manager,
            settings=settings,
            inference_client=inference_client,
            channel_selector=channel_selector,
            redis_conn=_redis_conn,
            calllog_buffer=_calllog_buffer,
            rate_limiter=rate_limiter,
            affinity_store=affinity_store,
        )

        health_redis_url = settings.channel_health_redis_url
        if not health_redis_url and _redis_conn is not None:
            health_redis_url = ""
        if health_redis_url:
            _health_refresh_task = asyncio.create_task(
                _health_cache_loop(health_redis_url, channel_selector, logger)
            )
        elif _redis_conn is not None:
            _health_refresh_task = asyncio.create_task(
                _health_cache_loop_shared(_redis_conn, channel_selector, logger)
            )

        log_event(logger, logging.INFO, "serviceReady", service="router-service")
        yield

        if _health_refresh_task is not None:
            _health_refresh_task.cancel()
            await asyncio.gather(_health_refresh_task, return_exceptions=True)
        if _calllog_buffer is not None:
            await _calllog_buffer.stop()
        await config_manager.stop()
        await inference_client.close()
        if _redis_conn is not None:
            await _redis_conn.aclose()
        log_event(logger, logging.INFO, "serviceStopping", service="router-service")

    app = FastAPI(
        title="Router Service",
        version="1.0.0",
        lifespan=lifespan,
    )

    from common.internal import build_internal_auth_dependency
    from common.internal_logs import build_internal_logs_router
    from common.observability import install_observability

    install_observability(app, service_name="router-service")

    app.include_router(meta.router)
    app.include_router(chat.router)
    app.include_router(completions.router)

    _logs_auth = build_internal_auth_dependency(
        settings.internal_secret,
        allowed_callers={"admin-service"},
    )
    app.include_router(build_internal_logs_router(_logs_auth))
    return app


async def _health_cache_loop(redis_url: str, selector: "ChannelSelector", logger: "logging.Logger") -> None:
    import asyncio
    import redis.asyncio as aioredis

    conn = None
    try:
        conn = aioredis.from_url(redis_url, decode_responses=True)
        await conn.ping()
        log_event(logger, logging.INFO, "healthCacheRedisConnected")
    except Exception:
        logger.warning("health cache Redis unavailable, running without health data")
        return

    try:
        await _health_cache_poll(conn, selector, logger)
    finally:
        if conn:
            await conn.aclose()


async def _health_cache_loop_shared(
    conn: "aioredis.Redis", selector: "ChannelSelector", logger: "logging.Logger",
) -> None:
    """Health cache loop using the shared Redis connection (no close on exit)."""
    import asyncio
    await _health_cache_poll(conn, selector, logger)


async def _health_cache_poll(conn, selector, logger) -> None:
    import asyncio
    import json

    while True:
        await asyncio.sleep(30)
        try:
            keys = []
            async for key in conn.scan_iter(match="channel_health:*", count=500):
                keys.append(key)
            if not keys:
                selector.update_health_cache({})
                continue
            values = await conn.mget(keys)
            cache: dict[str, str] = {}
            for key, val in zip(keys, values):
                if val is None:
                    continue
                suffix = key[len("channel_health:"):]
                try:
                    data = json.loads(val)
                    cache[suffix] = data.get("status", "unknown")
                except (json.JSONDecodeError, AttributeError):
                    pass
            selector.update_health_cache(cache)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("health cache refresh failed", exc_info=True)


app = create_app()


def cli():
    parser = argparse.ArgumentParser(description="Router Service")
    parser.add_argument("--host", type=str, default=DEFAULT_SERVICE_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SERVICE_PORT)
    parser.add_argument(
        "--runtime-config",
        type=str,
        default=_default_asset("runtime_config.json", "ROUTER_RUNTIME_CONFIG"),
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=os.getenv("ROUTER_LOG_DIR", os.getenv("LOG_DIR", "logs")),
    )
    args = parser.parse_args()

    import uvicorn

    cli_app = create_app(
        runtime_config_path=args.runtime_config,
        log_dir=args.log_dir,
    )

    print("=" * 60)
    print("starting router-service")
    print(f"  host: {args.host}")
    print(f"  port: {args.port}")
    print(f"  runtime config: {args.runtime_config}")
    print(f"  log dir: {args.log_dir}")
    print("=" * 60)

    uvicorn.run(cli_app, host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
