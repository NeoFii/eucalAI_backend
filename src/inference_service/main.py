"""FastAPI app creation + CLI entry point for inference-service."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI

from inference_service.config import (
    DEFAULT_INFERENCE_HOST,
    DEFAULT_INFERENCE_PORT,
    InferenceSettings,
    load_model_paths,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTER_ASSETS = _BACKEND_ROOT / "deploy" / "router"

# Global singletons
_engine: Optional[Any] = None
_runtime_store: Optional[Any] = None
_settings: Optional[InferenceSettings] = None

logger = logging.getLogger("inference_service")


def _default_asset(name: str, override_env: str) -> str:
    override = os.getenv(override_env)
    if override:
        return override
    return str(_DEFAULT_ROUTER_ASSETS / name)


def get_engine() -> Any:
    if _engine is None:
        raise RuntimeError("router engine not initialized")
    return _engine


def get_runtime_store() -> Any:
    if _runtime_store is None:
        raise RuntimeError("runtime store not initialized")
    return _runtime_store


def get_settings() -> InferenceSettings:
    if _settings is None:
        raise RuntimeError("settings not initialized")
    return _settings


def _setup_logging(log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)
    svc_logger = logging.getLogger("inference_service")
    if svc_logger.handlers:
        return
    svc_logger.setLevel(logging.INFO)
    svc_logger.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    svc_logger.addHandler(handler)


def create_app(
    runtime_config_path: str | None = None,
    model_paths_config: str | None = None,
    log_dir: str | None = None,
    settings: InferenceSettings | None = None,
) -> FastAPI:
    global _engine, _runtime_store, _settings

    _settings = settings or InferenceSettings.from_env()
    runtime_config_path = (
        runtime_config_path
        or _settings.runtime_config_path
        or _default_asset("runtime_config.json", "ROUTER_RUNTIME_CONFIG")
    )
    model_paths_config = (
        model_paths_config
        or _settings.model_paths_config
        or _default_asset("model_paths.json", "ROUTER_MODEL_PATHS")
    )
    log_dir = log_dir or _settings.log_dir

    _setup_logging(log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _engine, _runtime_store
        from inference_service.services.router_engine import HybridIntegratedDifficultyRouter
        from inference_service.utils.runtime_config import RuntimeConfigStore

        logger.info("initializing inference engine...")
        model_paths = load_model_paths(model_paths_config)
        _runtime_store = RuntimeConfigStore(runtime_config_path)
        _runtime_store.ensure_exists()
        _engine = HybridIntegratedDifficultyRouter(
            model_paths,
            runtime_config=_runtime_store.load(),
        )
        logger.info("inference engine ready")
        yield
        logger.info("shutting down")

    from inference_service.api import classify

    app = FastAPI(
        title="Inference Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(classify.router)

    @app.get("/ready")
    def ready() -> Dict[str, str]:
        return {"status": "ok", "service": "inference-service"}

    return app


app = create_app()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Inference Service")
    parser.add_argument("--host", type=str, default=DEFAULT_INFERENCE_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_INFERENCE_PORT)
    parser.add_argument(
        "--runtime-config",
        type=str,
        default=_default_asset("runtime_config.json", "ROUTER_RUNTIME_CONFIG"),
    )
    parser.add_argument(
        "--model-paths",
        type=str,
        default=_default_asset("model_paths.json", "ROUTER_MODEL_PATHS"),
    )
    parser.add_argument("--log-dir", type=str, default=os.getenv("INFERENCE_LOG_DIR", "logs"))
    args = parser.parse_args()

    import uvicorn

    cli_app = create_app(
        runtime_config_path=args.runtime_config,
        model_paths_config=args.model_paths,
        log_dir=args.log_dir,
    )

    print("=" * 60)
    print("starting inference-service")
    print(f"  host: {args.host}")
    print(f"  port: {args.port}")
    print(f"  runtime config: {args.runtime_config}")
    print(f"  model paths: {args.model_paths}")
    print(f"  log dir: {args.log_dir}")
    print("=" * 60)

    uvicorn.run(cli_app, host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
