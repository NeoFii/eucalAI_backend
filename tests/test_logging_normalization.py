"""Tests for normalized structured logging across services."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from common.core.exception_handlers import register_exception_handlers
from common.core.exceptions import APIException
from common.observability import configure_logging, install_observability, log_event


def _json_lines(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_configure_logging_emits_required_json_fields(capsys):
    configure_logging("INFO", service_name="unit-service")

    log_event(logging.getLogger("unit"), logging.INFO, "unit_event", answer=42)

    records = _json_lines(capsys.readouterr().out)
    assert len(records) == 1
    record = records[0]
    assert record["service"] == "unit-service"
    assert record["event"] == "unit_event"
    assert record["level"] == "INFO"
    assert record["request_id"] is None
    assert record["timestamp"].endswith("Z")
    assert record["answer"] == 42


def test_configure_logging_writes_optional_rotating_file(tmp_path: Path):
    configure_logging(
        "INFO",
        service_name="file-service",
        log_dir=str(tmp_path),
        enable_file_logging=True,
        file_prefix="file-service",
        file_max_bytes=1024,
        file_backup_count=2,
    )

    logging.getLogger("file-test").warning("plain warning")

    log_file = tmp_path / "file-service.log"
    assert log_file.exists()
    record = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert record["service"] == "file-service"
    assert record["event"] == "log"
    assert record["level"] == "WARNING"
    assert record["message"] == "plain warning"


def test_request_logging_includes_success_and_exception_fields(capsys):
    configure_logging("INFO", service_name="api-service")
    app = FastAPI()
    install_observability(app, service_name="api-service")

    @app.get("/ok")
    def _ok():
        return {"ok": True}

    @app.get("/boom")
    def _boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    ok_resp = client.get("/ok", headers={"X-Request-ID": "req-ok"})
    error_resp = client.get("/boom", headers={"X-Request-ID": "req-boom"})

    assert ok_resp.status_code == 200
    assert ok_resp.headers["X-Request-ID"] == "req-ok"
    assert error_resp.status_code == 500
    assert error_resp.headers["X-Request-ID"] == "req-boom"

    records = _json_lines(capsys.readouterr().out)
    by_request = {record["request_id"]: record for record in records}
    success = by_request["req-ok"]
    failure = by_request["req-boom"]

    assert success["event"] == "request_complete"
    assert success["status_code"] == 200
    assert success["method"] == "GET"
    assert success["path"] == "/ok"
    assert isinstance(success["duration_ms"], float)
    assert "client_ip" in success

    assert failure["event"] == "request_error"
    assert failure["status_code"] == 500
    assert failure["error_type"] == "RuntimeError"
    assert failure["path"] == "/boom"


class _Payload(BaseModel):
    name: str


def test_common_exception_handlers_log_api_validation_and_unhandled_errors(capsys):
    configure_logging("INFO", service_name="exception-service")
    app = FastAPI()
    install_observability(app, service_name="exception-service")
    register_exception_handlers(app)

    @app.get("/api-error")
    def _api_error():
        raise APIException(status_code=409, detail="conflict")

    @app.post("/validation")
    def _validation(payload: _Payload):
        return payload

    @app.get("/unhandled")
    def _unhandled():
        raise RuntimeError("broken")

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api-error", headers={"X-Request-ID": "rid-api"}).status_code == 409
    assert (
        client.post(
            "/validation",
            json={"name": 123},
            headers={"X-Request-ID": "rid-validation"},
        ).status_code
        == 422
    )
    assert client.get("/unhandled", headers={"X-Request-ID": "rid-unhandled"}).status_code == 500

    records = _json_lines(capsys.readouterr().out)
    events = {(record["request_id"], record["event"]) for record in records}
    assert ("rid-api", "api_exception") in events
    assert ("rid-validation", "validation_error") in events
    assert ("rid-unhandled", "unhandled_exception") in events


def test_inference_error_handlers_emit_structured_logs(capsys):
    from inference_service.error_handlers import install_error_handlers
    from inference_service.schemas.errors import InferenceAuthError

    configure_logging("INFO", service_name="inference_service")
    app = FastAPI()
    install_observability(app, service_name="inference_service")
    install_error_handlers(app)

    @app.get("/auth")
    def _auth():
        raise InferenceAuthError("forbidden")

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/auth", headers={"X-Request-ID": "rid-inf"}).status_code == 403

    records = _json_lines(capsys.readouterr().out)
    assert any(
        record["event"] == "inference_error"
        and record["request_id"] == "rid-inf"
        and record["error_code"] == "auth"
        for record in records
    )


def test_router_jsonl_logs_have_standard_fields_and_redacted_previews(tmp_path: Path):
    import router_service.logging as router_logging

    router_logging._initialized = False
    router_logging.setup_logging(log_dir=str(tmp_path), level="INFO")

    router_logging.log_routing_decision(
        request_id="rid-router",
        router_trace_id="trace-1",
        requested_model="auto",
        selected_model="gpt-4",
        input_preview="password=secret api_key=sk-live-1234567890 " + "x" * 500,
    )
    router_logging.log_upstream_call(
        request_id="rid-router",
        router_trace_id="trace-1",
        selected_model="gpt-4",
        provider_slug="openai",
        upstream_model="gpt-4o",
        api_base="https://api.openai.com",
        response_preview="Bearer sk-live-token and token=abc123 " + "y" * 500,
    )

    routing = json.loads((tmp_path / "routing.jsonl").read_text(encoding="utf-8").strip())
    upstream = json.loads((tmp_path / "upstream.jsonl").read_text(encoding="utf-8").strip())

    assert routing["service"] == "router_service"
    assert routing["event"] == "routing_decision"
    assert routing["request_id"] == "rid-router"
    assert routing["router_trace_id"] == "trace-1"
    assert routing["ts"].endswith("Z")
    assert len(routing["input_preview"]) <= router_logging.INPUT_PREVIEW_MAX_CHARS
    assert "secret" not in routing["input_preview"]
    assert "sk-live" not in routing["input_preview"]
    assert "[REDACTED]" in routing["input_preview"]

    assert upstream["service"] == "router_service"
    assert upstream["event"] == "upstream_call"
    assert upstream["request_id"] == "rid-router"
    assert upstream["router_trace_id"] == "trace-1"
    assert len(upstream["response_preview"]) <= router_logging.RESPONSE_PREVIEW_MAX_CHARS
    assert "sk-live" not in upstream["response_preview"]
    assert "abc123" not in upstream["response_preview"]


def test_router_and_inference_settings_read_logging_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "shared-logs"))
    monkeypatch.setenv("LOG_TO_FILE", "true")
    monkeypatch.setenv("LOG_FILE_MAX_BYTES", "4096")
    monkeypatch.setenv("LOG_FILE_BACKUP_COUNT", "7")
    monkeypatch.delenv("ROUTER_LOG_DIR", raising=False)
    monkeypatch.delenv("INFERENCE_LOG_DIR", raising=False)

    from inference_service.config import InferenceSettings
    from router_service.settings import RouterSettings

    router = RouterSettings.from_env()
    inference = InferenceSettings.from_env()

    assert router.log_level == "DEBUG"
    assert router.log_dir == str(tmp_path / "shared-logs")
    assert router.log_to_file is True
    assert router.log_file_max_bytes == 4096
    assert router.log_file_backup_count == 7

    assert inference.log_level == "DEBUG"
    assert inference.log_dir == str(tmp_path / "shared-logs")
    assert inference.log_to_file is True
    assert inference.log_file_max_bytes == 4096
    assert inference.log_file_backup_count == 7


def test_compose_files_wire_logging_environment_to_log_volumes():
    repo_root = Path(__file__).resolve().parent.parent
    backend_compose = (repo_root / "deploy" / "docker-compose.backend.yml").read_text(
        encoding="utf-8"
    )
    router_compose = (repo_root / "deploy" / "docker-compose.router.yml").read_text(
        encoding="utf-8"
    )
    inference_compose = (repo_root / "deploy" / "docker-compose.inference.yml").read_text(
        encoding="utf-8"
    )

    for compose in (backend_compose, router_compose, inference_compose):
        assert "LOG_LEVEL: ${LOG_LEVEL:-INFO}" in compose
        assert "LOG_TO_FILE: ${LOG_TO_FILE:-true}" in compose
        assert "LOG_FILE_MAX_BYTES: ${LOG_FILE_MAX_BYTES:-52428800}" in compose
        assert "LOG_FILE_BACKUP_COUNT: ${LOG_FILE_BACKUP_COUNT:-5}" in compose

    assert 'LOG_DIR: "/app/logs"' in backend_compose
    assert 'ROUTER_LOG_DIR: "/app/logs"' in router_compose
    assert 'INFERENCE_LOG_DIR: "/app/logs"' in inference_compose
