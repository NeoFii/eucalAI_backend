"""FastAPI app creation + CLI entry point."""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from router_service.config import (
    DEFAULT_SERVICE_HOST,
    DEFAULT_SERVICE_PORT,
    load_model_paths,
)
from router_service.deps import init_globals
from router_service.logging import setup_logging, get_app_logger
from router_service.routers import chat, completions, meta


def create_app(
    runtime_config_path: str = "runtime_config.json",
    model_paths_config: str = "model_paths.json",
    log_dir: str = "logs",
) -> FastAPI:
    setup_logging(log_dir=log_dir)
    logger = get_app_logger()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("initializing router engine...")
        model_paths = load_model_paths(model_paths_config)
        init_globals(
            runtime_config_path=runtime_config_path,
            model_paths=model_paths,
        )
        logger.info("router engine ready")
        yield
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


def cli():
    parser = argparse.ArgumentParser(description="Router Service")
    parser.add_argument("--host", type=str, default=DEFAULT_SERVICE_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SERVICE_PORT)
    parser.add_argument("--runtime-config", type=str, default="runtime_config.json")
    parser.add_argument("--model-paths", type=str, default="model_paths.json")
    parser.add_argument("--log-dir", type=str, default="logs")
    args = parser.parse_args()

    import uvicorn

    app = create_app(
        runtime_config_path=args.runtime_config,
        model_paths_config=args.model_paths,
        log_dir=args.log_dir,
    )

    print("=" * 60)
    print("starting router-service")
    print(f"  host: {args.host}")
    print(f"  port: {args.port}")
    print(f"  runtime config: {args.runtime_config}")
    print(f"  model paths: {args.model_paths}")
    print(f"  log dir: {args.log_dir}")
    print("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
