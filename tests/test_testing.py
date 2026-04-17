from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

os.environ["TESTING_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"
os.environ["INTERNAL_SECRET"] = "test_internal_secret"


class TestTestingModels:
    def test_import_current_models(self):
        from testing_service.models import (
            AdminProbeAuditLog,
            BenchmarkJob,
            Model,
            ModelCategory,
            ModelCategoryMap,
            ModelProviderOffering,
            Provider,
            ProviderPerformanceMetric,
            SERVICE_MODELS,
        )

        assert ModelCategory is not None
        assert Model is not None
        assert Provider is not None
        assert ModelCategoryMap is not None
        assert ModelProviderOffering is not None
        assert ProviderPerformanceMetric is not None
        assert BenchmarkJob is not None
        assert AdminProbeAuditLog is not None
        assert SERVICE_MODELS


class TestTestingSchemas:
    def test_import_current_schemas(self):
        from testing_service.schemas import ApiResponse, ListResponse, ModelCreate, ProviderCreate

        assert ApiResponse is not None
        assert ListResponse is not None
        assert ModelCreate is not None
        assert ProviderCreate is not None

    def test_model_create_schema_fields(self):
        from testing_service.schemas import ModelCategoryAssign, ModelCreate

        schema = ModelCreate(
            vendor_id=1,
            slug="test-model",
            name="Test Model",
            categories=[ModelCategoryAssign(category_id=2, sort_order=3)],
        )

        assert schema.vendor_id == 1
        assert schema.slug == "test-model"
        assert schema.categories[0].category_id == 2

    def test_provider_create_schema_fields(self):
        from testing_service.schemas import ProviderCreate

        schema = ProviderCreate(slug="test-provider", name="Test Provider")

        assert schema.slug == "test-provider"
        assert schema.name == "Test Provider"
        assert schema.is_active is True


class TestTestingConfig:
    def test_settings_defaults(self):
        from testing_service.config import Settings

        settings = Settings()

        assert settings.host == "0.0.0.0"
        assert settings.port == 8002
        assert settings.benchmark_default_timeout == 60
        assert settings.benchmark_default_concurrency == 10
        assert settings.cache_ttl_short == 300
        assert settings.cache_ttl_long == 86400
        assert settings.DATABASE_URL


class TestTestingModules:
    def test_import_explicit_service_modules(self):
        from testing_service.benchmarking import AdminProbeAuditService, BenchmarkJobService
        from testing_service.catalog import CategoryService, ModelService, VendorService
        from testing_service.provider_config import OfferingService, PerformanceMetricService, ProviderService

        assert CategoryService is not None
        assert ModelService is not None
        assert VendorService is not None
        assert ProviderService is not None
        assert OfferingService is not None
        assert PerformanceMetricService is not None
        assert BenchmarkJobService is not None
        assert AdminProbeAuditService is not None

    def test_benchmark_task_exports(self):
        from testing_service.benchmark.tasks import ProbeScheduler, ProbeTask

        assert hasattr(ProbeTask, "probe_offering")
        assert hasattr(ProbeTask, "probe_all_active")
        assert hasattr(ProbeScheduler, "run_scheduled_probe")

    def test_benchmark_engine_exports(self):
        from testing_service.benchmark.engine import BenchmarkEngine

        engine = BenchmarkEngine()
        assert hasattr(engine, "run_benchmark")


class TestTestingApi:
    def test_api_router_import(self):
        from testing_service.api.v1.router import api_router

        route_paths = {route.path for route in api_router.routes}
        assert "/api/v1/models" in route_paths
        assert "/api/v1/models/" in route_paths
        assert "/api/v1/providers" in route_paths
        assert "/api/v1/benchmark/probe/trigger" in route_paths

    def test_models_list_accepts_trailing_slash(self, monkeypatch):
        from testing_service.dependencies import get_db_session
        from testing_service.api.v1.endpoints import models

        async def _fake_db():
            yield SimpleNamespace()

        async def _fake_list_all(**kwargs):
            assert kwargs["page"] == 1
            assert kwargs["page_size"] == 100
            return [], 0

        monkeypatch.setattr(models.ModelService, "list_all", _fake_list_all)

        app = FastAPI(redirect_slashes=False)
        app.include_router(models.router, prefix="/api/v1")
        app.dependency_overrides[get_db_session] = _fake_db
        client = TestClient(app)

        plain = client.get("/api/v1/models", params={"page": 1, "page_size": 100})
        trailing = client.get("/api/v1/models/", params={"page": 1, "page_size": 100})

        assert plain.status_code == 200
        assert trailing.status_code == 200
        assert plain.json()["data"]["items"] == []
        assert trailing.json()["data"]["items"] == []

    def test_benchmark_summary_is_public(self, monkeypatch):
        from testing_service.dependencies import get_db_session
        from testing_service.api.v1.endpoints import benchmark

        async def _fake_db():
            yield SimpleNamespace()

        async def _fake_list_all_active(db):
            return []

        monkeypatch.setattr(benchmark.OfferingService, "list_all_active", _fake_list_all_active)

        app = FastAPI(redirect_slashes=False)
        app.include_router(benchmark.router, prefix="/api/v1")
        app.dependency_overrides[get_db_session] = _fake_db
        client = TestClient(app)

        response = client.get("/api/v1/benchmark/stats/summary", params={"n": 5})

        assert response.status_code == 200
        assert response.json()["data"]["items"] == []
        assert response.json()["data"]["total"] == 0

    def test_benchmark_trends_is_public(self, monkeypatch):
        from testing_service.dependencies import get_db_session
        from testing_service.api.v1.endpoints import benchmark

        async def _fake_db():
            yield SimpleNamespace()

        async def _fake_get_by_slug(db, model_slug):
            assert model_slug == "demo-model"
            return None

        monkeypatch.setattr(benchmark.ModelService, "get_by_slug", _fake_get_by_slug)

        app = FastAPI(redirect_slashes=False)
        app.include_router(benchmark.router, prefix="/api/v1")
        app.dependency_overrides[get_db_session] = _fake_db
        client = TestClient(app)

        response = client.get("/api/v1/benchmark/trends", params={"model_slug": "demo-model", "days": 7})

        assert response.status_code == 200
        assert response.json()["data"]["model_slug"] == "demo-model"
        assert response.json()["data"]["providers"] == []

    def test_benchmark_import(self):
        from testing_service.api.v1.endpoints import benchmark

        assert hasattr(benchmark, "trigger_probe_all")
        assert hasattr(benchmark, "get_benchmark_stats_summary")

    def test_main_and_worker_import(self):
        from testing_service.config import get_settings
        from testing_service.main import app
        from testing_service.worker import WorkerSettings

        assert app.title == get_settings().PROJECT_NAME
        assert hasattr(WorkerSettings, "functions")
        assert hasattr(WorkerSettings, "redis_settings")

    def test_worker_import_in_fresh_python_process(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = backend_dir
        result = subprocess.run(
            [sys.executable, "-c", "import testing_service.worker"],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr or result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
