"""Tests for VNext-B inference-service structured error responses."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_service.error_handlers import install_error_handlers
from inference_service.schemas.errors import (
    InferenceAuthError,
    InferenceConfigError,
    InferenceUnavailableError,
)


def _build_test_app() -> FastAPI:
    from common.observability import install_observability

    app = FastAPI()
    install_observability(app, service_name="inference_service")
    install_error_handlers(app)

    @app.get("/test-auth-error")
    def _auth():
        raise InferenceAuthError("forbidden")

    @app.get("/test-config-error")
    def _config():
        raise InferenceConfigError("config not available")

    @app.get("/test-unavailable-error")
    def _unavailable():
        raise InferenceUnavailableError("service not ready")

    @app.get("/test-runtime-error")
    def _runtime():
        raise RuntimeError("CUDA out of memory")

    @app.post("/test-validation")
    def _validation(data: dict):
        return data

    return app


@pytest.fixture
def client():
    app = _build_test_app()
    return TestClient(app, raise_server_exceptions=False)


def test_auth_error_structured_403(client):
    resp = client.get("/test-auth-error")
    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == "auth"
    assert "forbidden" in body["message"]


def test_config_error_structured_503(client):
    resp = client.get("/test-config-error")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "config"


def test_unavailable_error_structured_503(client):
    resp = client.get("/test-unavailable-error")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "unavailable"


def test_model_runtime_error_structured_500(client):
    resp = client.get("/test-runtime-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error_code"] == "model_runtime"


def test_cuda_oom_classified_as_model_runtime(client):
    resp = client.get("/test-runtime-error")
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "model_runtime"


def test_validation_error_structured_422(client):
    resp = client.post("/test-validation", content="not json", headers={"content-type": "application/json"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation"


def test_error_response_has_request_id(client):
    resp = client.get("/test-auth-error", headers={"X-Request-ID": "test-rid-123"})
    body = resp.json()
    assert body.get("request_id") == "test-rid-123"
