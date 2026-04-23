"""Tests for VNext-B observability and request_id propagation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common.observability import install_observability


def _build_test_app() -> FastAPI:
    app = FastAPI()
    install_observability(app, service_name="router_service")

    @app.get("/test-echo")
    def _echo():
        from common.observability import get_request_id
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
def client():
    return TestClient(_build_test_app())


def test_router_sets_request_id_header(client):
    resp = client.get("/test-echo")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_router_preserves_request_id(client):
    resp = client.get("/test-echo", headers={"X-Request-ID": "my-custom-rid"})
    assert resp.headers["X-Request-ID"] == "my-custom-rid"
    assert resp.json()["request_id"] == "my-custom-rid"


def test_classify_result_has_config_fields():
    from router_service.services.inference_client import ClassifyResult

    result = ClassifyResult(success=True, data={"selected_model": "test"})
    assert result.success is True
    assert result.data["selected_model"] == "test"
    assert result.error_code is None


def test_classify_result_error_fields():
    from router_service.services.inference_client import ClassifyResult

    result = ClassifyResult(
        success=False,
        error_code="unavailable",
        error_message="service down",
        http_status=503,
    )
    assert result.success is False
    assert result.error_code == "unavailable"
    assert result.http_status == 503
