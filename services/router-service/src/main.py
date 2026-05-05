"""FastAPI app creation + CLI entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from common.core.exception_handlers import register_exception_handlers
from common.observability import log_event
from core.config import get_settings
from core.dependencies import init_globals
from core.router import api_router
from utils.logging_config import get_app_logger, setup_logging

_DEFAULT_ROUTER_ASSETS = Path.cwd() / "config"


def _default_asset(name: str, override_env: str) -> str:
    override = os.getenv(override_env)
    if override:
        return override
    return str(_DEFAULT_ROUTER_ASSETS / name)


def create_app(
    runtime_config_path: str | None = None,
    log_dir: str | None = None,
) -> FastAPI:
    from gateways.admin_config import AdminConfigGateway
    from gateways.calllog_batch import BatchCallLogGateway
    from services.config_manager import ConfigManager
    from services.inference_client import InferenceClient
    from services.channel_selector import ChannelSelector

    settings = get_settings()
    runtime_config_path = runtime_config_path or _default_asset(
        "runtime_config.json", "ROUTER_RUNTIME_CONFIG"
    )
    log_dir = log_dir or settings.LOG_DIR

    setup_logging(
        log_dir=log_dir,
        level=settings.LOG_LEVEL,
        env=settings.ENV,
        enable_file_logging=settings.LOG_TO_FILE,
        file_max_bytes=settings.LOG_FILE_MAX_BYTES,
        file_backup_count=settings.LOG_FILE_BACKUP_COUNT,
        ring_buffer_capacity=int(os.getenv("LOG_RING_BUFFER_CAPACITY", "2000")),
    )
    logger = get_app_logger()

    admin_gateway = AdminConfigGateway(settings)
    batch_calllog_gateway = BatchCallLogGateway(settings)

    inference_client = InferenceClient(
        base_url=settings.INFERENCE_SERVICE_URL,
        secret=settings.INFERENCE_SERVICE_SECRET,
        max_retries=settings.INTERNAL_HTTP_MAX_RETRIES,
        retry_backoff=settings.INTERNAL_HTTP_RETRY_BACKOFF_SECONDS,
        circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
        circuit_breaker_cooldown=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    )

    config_manager = ConfigManager(
        settings=settings,
        runtime_config_path=runtime_config_path,
        admin_gateway=admin_gateway,
    )

    channel_selector = ChannelSelector(
        cooldown_seconds=settings.CHANNEL_COOLDOWN_SECONDS,
        auto_disable_enabled=settings.CHANNEL_AUTO_DISABLE_ENABLED,
        auto_disable_threshold=settings.CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD,
        auto_disable_cooldown_seconds=settings.CHANNEL_AUTO_DISABLE_COOLDOWN_SECONDS,
    )

    _health_refresh_task = None
    _redis_conn = None
    _calllog_buffer = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        from common.internal import InternalHttpPool

        nonlocal _health_refresh_task, _redis_conn, _calllog_buffer
        log_event(logger, logging.INFO, "serviceStarting", service="router-service")

        await InternalHttpPool.init(
            max_connections=100,
            max_keepalive_connections=20,
            default_timeout=10.0,
        )
        await config_manager.start()

        if settings.ROUTER_REDIS_URL:
            import redis.asyncio as aioredis
            try:
                _redis_conn = aioredis.from_url(settings.ROUTER_REDIS_URL, decode_responses=True)
                await _redis_conn.ping()
                log_event(logger, logging.INFO, "redisConnected", url=settings.ROUTER_REDIS_URL)
            except Exception:
                logger.warning("Redis unavailable at %s, features will degrade to in-memory", settings.ROUTER_REDIS_URL)
                _redis_conn = None
        from services.calllog_buffer import CallLogBuffer
        _calllog_buffer = CallLogBuffer(
            settings=settings,
            flush_interval=settings.CALLLOG_FLUSH_INTERVAL,
            max_buffer=settings.CALLLOG_MAX_BUFFER,
            max_retries=settings.CALLLOG_MAX_RETRIES,
            batch_gateway=batch_calllog_gateway,
        )
        await _calllog_buffer.start()

        rate_limiter = None
        if settings.RATE_LIMIT_ENABLED:
            from services.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                redis=_redis_conn,
                default_user_rpm=settings.RATE_LIMIT_DEFAULT_USER_RPM,
                global_rpm=settings.RATE_LIMIT_GLOBAL_RPM,
            )

        affinity_store = None
        if settings.CHANNEL_AFFINITY_ENABLED:
            from services.channel_affinity import ChannelAffinityStore
            affinity_store = ChannelAffinityStore(
                redis=_redis_conn,
                ttl=settings.CHANNEL_AFFINITY_TTL,
                lru_maxsize=settings.CHANNEL_AFFINITY_LRU_MAXSIZE,
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

        health_redis_url = settings.CHANNEL_HEALTH_REDIS_URL
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
        await InternalHttpPool.close()
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
    register_exception_handlers(app)

    app.include_router(api_router)

    _logs_auth = build_internal_auth_dependency(
        settings.INTERNAL_SECRET,
        allowed_callers={"admin-service"},
    )
    app.include_router(build_internal_logs_router(_logs_auth))
    return app


async def _health_cache_loop(redis_url: str, selector, logger) -> None:
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


async def _health_cache_loop_shared(conn, selector, logger) -> None:
    """Health cache loop using the shared Redis connection (no close on exit)."""
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
    import argparse
    import uvicorn

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Router Service")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=settings.PORT)
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
