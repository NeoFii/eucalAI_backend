"""FastAPI app creation + CLI entry point for inference-service."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI

from common.observability import configure_logging, log_event
from inference_service.config import (
    DEFAULT_INFERENCE_HOST,
    DEFAULT_INFERENCE_PORT,
    InferenceSettings,
    load_model_paths,
)
from inference_service.schemas.errors import InferenceUnavailableError

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTER_ASSETS = _SERVICE_ROOT / "config"

# Global singletons
_engine: Optional[Any] = None
_config_manager: Optional[Any] = None
_settings: Optional[InferenceSettings] = None

logger = logging.getLogger("inference_service")


def _default_asset(name: str, override_env: str) -> str:
    override = os.getenv(override_env)
    if override:
        return override
    return str(_DEFAULT_ROUTER_ASSETS / name)


def get_engine() -> Any:
    if _engine is None:
        raise InferenceUnavailableError("router engine not initialized")
    return _engine


def get_runtime_store() -> Any:
    if _config_manager is None:
        raise InferenceUnavailableError("config manager not initialized")
    return _config_manager


def get_config_manager() -> Any:
    if _config_manager is None:
        raise InferenceUnavailableError("config manager not initialized")
    return _config_manager


def get_settings() -> InferenceSettings:
    if _settings is None:
        raise RuntimeError("settings not initialized")
    return _settings


def create_app(
    runtime_config_path: str | None = None,
    model_paths_config: str | None = None,
    log_dir: str | None = None,
    settings: InferenceSettings | None = None,
) -> FastAPI:
    global _engine, _config_manager, _settings

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

    configure_logging(
        _settings.log_level,
        service_name="inference-service",
        env=_settings.env,
        log_dir=log_dir,
        enable_file_logging=_settings.log_to_file,
        file_prefix="inference_service",
        file_max_bytes=_settings.log_file_max_bytes,
        file_backup_count=_settings.log_file_backup_count,
        ring_buffer_capacity=int(os.getenv("LOG_RING_BUFFER_CAPACITY", "2000")),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _engine, _config_manager
        from inference_service.services.config_manager import ConfigManager
        from inference_service.services.router_engine import HybridIntegratedDifficultyRouter

        log_event(logger, logging.INFO, "serviceStarting", service="inference-service")
        model_paths = load_model_paths(model_paths_config)

        config_mgr = ConfigManager(
            settings=_settings,
            runtime_config_path=runtime_config_path,
        )
        await config_mgr.start()
        _config_manager = config_mgr

        _engine = HybridIntegratedDifficultyRouter(
            model_paths,
            runtime_config=config_mgr.load(),
        )
        log_event(logger, logging.INFO, "serviceReady", service="inference-service")
        yield
        await config_mgr.stop()
        log_event(logger, logging.INFO, "serviceStopping", service="inference-service")

    from inference_service.api import classify

    app = FastAPI(
        title="Inference Service",
        version="1.0.0",
        lifespan=lifespan,
    )

    from common.internal import build_internal_auth_dependency
    from common.internal_logs import build_internal_logs_router
    from common.observability import install_observability
    from inference_service.error_handlers import install_error_handlers

    install_observability(app, service_name="inference-service")
    install_error_handlers(app)

    app.include_router(classify.router)

    _logs_auth = build_internal_auth_dependency(
        _settings.internal_secret,
        allowed_callers={"admin-service"},
    )
    app.include_router(build_internal_logs_router(_logs_auth))

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
    parser.add_argument(
        "--log-dir",
        type=str,
        default=os.getenv("INFERENCE_LOG_DIR", os.getenv("LOG_DIR", "logs")),
    )
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
