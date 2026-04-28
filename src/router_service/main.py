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

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTER_ASSETS = _BACKEND_ROOT / "deploy" / "router"


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

    channel_selector = ChannelSelector()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_event(logger, logging.INFO, "serviceStarting", service="router-service")
        await config_manager.start()
        init_globals(
            config_manager=config_manager,
            settings=settings,
            inference_client=inference_client,
            channel_selector=channel_selector,
        )
        log_event(logger, logging.INFO, "serviceReady", service="router-service")
        yield
        await config_manager.stop()
        await inference_client.close()
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
