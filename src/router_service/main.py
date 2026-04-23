"""FastAPI app creation + CLI entry point."""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from router_service.config import DEFAULT_SERVICE_HOST, DEFAULT_SERVICE_PORT
from router_service.dependencies import init_globals
from router_service.logging import setup_logging, get_app_logger
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
    from router_service.services.inference_client import InferenceClient
    from router_service.settings import RouterSettings

    settings = RouterSettings.from_env()
    runtime_config_path = runtime_config_path or _default_asset(
        "runtime_config.json", "ROUTER_RUNTIME_CONFIG"
    )
    log_dir = log_dir or os.getenv("ROUTER_LOG_DIR", "logs")

    setup_logging(log_dir=log_dir)
    logger = get_app_logger()

    inference_client = InferenceClient(
        base_url=settings.inference_service_url,
        secret=settings.inference_service_secret,
        max_retries=settings.internal_http_max_retries,
        retry_backoff=settings.internal_http_retry_backoff_seconds,
        circuit_breaker_threshold=settings.internal_http_circuit_breaker_threshold,
        circuit_breaker_cooldown=settings.internal_http_circuit_breaker_cooldown_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("initializing router gateway...")
        init_globals(
            runtime_config_path=runtime_config_path,
            settings=settings,
            inference_client=inference_client,
        )
        logger.info("router gateway ready")
        yield
        await inference_client.close()
        logger.info("shutting down")

    app = FastAPI(
        title="Router Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(meta.router)
    app.include_router(chat.router)
    app.include_router(completions.router)
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
    parser.add_argument("--log-dir", type=str, default=os.getenv("ROUTER_LOG_DIR", "logs"))
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
