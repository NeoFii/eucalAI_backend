from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

ROOT = Path(__file__).resolve().parent.parent
SERVICE_MAIN_FILES = (
    ROOT / "src" / "admin_service" / "main.py",
    ROOT / "src" / "testing_service" / "main.py",
)


def test_service_entrypoints_install_observability_and_readiness_routes():
    for path in SERVICE_MAIN_FILES:
        source = path.read_text(encoding="utf-8")
        assert "install_observability(app, service_name=settings.SERVICE_NAME)" in source
        assert '@app.get("/ready"' in source
        assert "build_readiness_response(" in source
        assert "init_db(" not in source
        assert "AUTO_INIT_DB" not in source


def test_observability_middleware_propagates_request_id():
    from common.observability import REQUEST_ID_HEADER, install_observability

    app = FastAPI()
    install_observability(app, service_name="phase4-test-service")

    @app.get("/ping")
    async def ping():
        return JSONResponse({"ok": True})

    client = TestClient(app)
    response = client.get("/ping", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-123"


@pytest.mark.asyncio
async def test_build_readiness_response_reports_database_state():
    from common.health import build_readiness_response

    response = await build_readiness_response(
        service_name="phase4-test-service",
        database_check=lambda: _ready_check(True, None),
    )

    assert response.status_code == 200
    assert b'"status":"ready"' in response.body
    assert b'"database":{"status":"ok","detail":null}' in response.body

    failing = await build_readiness_response(
        service_name="phase4-test-service",
        database_check=lambda: _ready_check(False, "db down"),
    )

    assert failing.status_code == 503
    assert b'"status":"not_ready"' in failing.body
    assert b'"detail":"db down"' in failing.body


async def _ready_check(ok: bool, detail: str | None):
    return ok, detail


def test_readme_documents_phase4_runtime_capabilities():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Phase 4 Status" in readme
    assert "/ready" in readme
    assert "X-Request-ID" in readme
    assert "signed internal" in readme.lower()


def test_runtime_docs_define_api_readiness_worker_probes_and_migration_ownership():
    runtime_contracts = (ROOT / "docs" / "service-runtime-contracts.md").read_text(encoding="utf-8")
    phase4_ops = (ROOT / "docs" / "phase4-operations.md").read_text(encoding="utf-8")

    assert "testing-worker" in runtime_contracts
    assert "scripts/runtime_probe.py worker-ready" in runtime_contracts
    assert "TESTING_DATABASE_URL" in runtime_contracts
    assert "BENCHMARK_QUEUE_REDIS_URL" in phase4_ops
    assert "generic `DATABASE_URL`" in phase4_ops
    assert "scripts/runtime_probe.py worker-ready" in phase4_ops
