"""FastAPI app creation + CLI entry point for inference-service."""

from __future__ import annotations

import argparse
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI

from common.observability import configure_logging, log_event
from inference_service.core.config import get_settings, load_model_paths
from inference_service.core.dependencies import set_config_manager, set_engine
from inference_service.core.exceptions import install_inference_error_handlers
from inference_service.core.router import api_router

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTER_ASSETS = _SERVICE_ROOT / "config"

logger = logging.getLogger("inference_service")


def _resolve_asset(setting_value: str, filename: str) -> str:
    if setting_value:
        return setting_value
    return str(_DEFAULT_ROUTER_ASSETS / filename)


def create_app() -> FastAPI:
    settings = get_settings()

    configure_logging(
        settings.LOG_LEVEL,
        service_name=settings.SERVICE_NAME,
        env=settings.ENV,
        log_dir=settings.LOG_DIR,
        enable_file_logging=settings.LOG_TO_FILE,
        file_prefix="inference_service",
        file_max_bytes=settings.LOG_FILE_MAX_BYTES,
        file_backup_count=settings.LOG_FILE_BACKUP_COUNT,
        ring_buffer_capacity=settings.LOG_RING_BUFFER_CAPACITY,
    )

    runtime_config_path = _resolve_asset(settings.ROUTER_RUNTIME_CONFIG, "runtime_config.json")
    model_paths_config = _resolve_asset(settings.ROUTER_MODEL_PATHS, "model_paths.json")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from common.internal import close_internal_clients
        from inference_service.gateways.admin_config import AdminConfigGateway
        from inference_service.services.classify_service import init_gpu_semaphore
        from inference_service.services.config_manager import ConfigManager
        from inference_service.services.router_engine import HybridIntegratedDifficultyRouter

        log_event(logger, logging.INFO, "serviceStarting", service=settings.SERVICE_NAME)
        model_paths = load_model_paths(model_paths_config)

        gateway = AdminConfigGateway()
        config_mgr = ConfigManager(
            gateway=gateway,
            runtime_config_path=runtime_config_path,
            refresh_interval_seconds=settings.CONFIG_REFRESH_INTERVAL_SECONDS,
        )
        await config_mgr.start()
        set_config_manager(config_mgr)

        engine = HybridIntegratedDifficultyRouter(
            model_paths,
            runtime_config=config_mgr.load(),
        )
        set_engine(engine)

        init_gpu_semaphore(settings.GPU_CONCURRENCY_LIMIT)

        log_event(logger, logging.INFO, "serviceReady", service=settings.SERVICE_NAME)
        yield
        await config_mgr.stop()
        engine.cleanup()
        await close_internal_clients()
        log_event(logger, logging.INFO, "serviceStopping", service=settings.SERVICE_NAME)

    from common.internal import build_internal_auth_dependency
    from common.internal_logs import build_internal_logs_router
    from common.observability import install_observability

    app = FastAPI(
        title="Inference Service",
        version=settings.VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    install_observability(app, service_name=settings.SERVICE_NAME)
    install_inference_error_handlers(app)

    app.include_router(api_router)

    _logs_auth = build_internal_auth_dependency(
        settings.INTERNAL_SECRET,
        allowed_callers={"admin-service"},
    )
    app.include_router(build_internal_logs_router(_logs_auth))

    @app.get("/ready")
    def ready() -> Dict[str, str]:
        return {"status": "ok", "service": settings.SERVICE_NAME}

    return app


app = create_app()


def cli() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Inference Service")
    parser.add_argument("--host", type=str, default=settings.INFERENCE_HOST)
    parser.add_argument("--port", type=int, default=settings.PORT)
    args = parser.parse_args()

    import uvicorn

    print("=" * 60)
    print("starting inference-service")
    print(f"  host: {args.host}")
    print(f"  port: {args.port}")
    print("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
