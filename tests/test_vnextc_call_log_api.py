"""Tests for VNext-C user-service internal call-log API (POST + PATCH)."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("INTERNAL_SECRET", "test_internal_secret_32chars_long!")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common.internal import build_internal_headers


def _internal_secret() -> str:
    from user_service.api.v1.endpoints import internal
    return internal.settings.INTERNAL_SECRET


class _ScalarResult:
    def __init__(self, *, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        if self._value is None:
            raise Exception("no row")
        return self._value


class FakeSession:
    """In-memory fake that tracks add/commit/refresh/rollback calls."""

    def __init__(self):
        self._store: dict[str, SimpleNamespace] = {}
        self._pending_add: SimpleNamespace | None = None
        self._committed = False
        self._raise_integrity = False

    async def execute(self, statement):
        req_id = _extract_request_id(statement)
        return _ScalarResult(value=self._store.get(req_id))

    def add(self, obj):
        self._pending_add = obj

    async def commit(self):
        if self._raise_integrity:
            from sqlalchemy.exc import IntegrityError
            self._raise_integrity = False
            raise IntegrityError("duplicate", {}, None)
        if self._pending_add is not None:
            obj = self._pending_add
            obj.id = 100001
            self._store[obj.request_id] = obj
            self._pending_add = None
        self._committed = True

    async def rollback(self):
        self._pending_add = None

    async def refresh(self, obj):
        pass


def _extract_request_id(stmt) -> str | None:
    """Extract the request_id bind value from a SQLAlchemy select statement."""
    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
        import re
        m = re.search(r"request_id\s*=\s*'([^']+)'", sql_str)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _build_app():
    from user_service.api.v1.endpoints import internal
    from user_service.dependencies import get_db_session

    app = FastAPI()
    app.include_router(internal.router, prefix="/api/v1")
    return app, get_db_session


def _make_client(fake_session):
    app, get_db_session = _build_app()

    async def _fake_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = _fake_db
    return TestClient(app, raise_server_exceptions=False)


def _router_headers(method: str, path: str, json_body: dict | None = None) -> dict:
    return build_internal_headers(
        secret=_internal_secret(),
        caller_service="router-service",
        method=method,
        path=path,
        json_body=json_body,
    )


def _admin_headers(method: str, path: str, json_body: dict | None = None) -> dict:
    return build_internal_headers(
        secret=_internal_secret(),
        caller_service="admin-service",
        method=method,
        path=path,
        json_body=json_body,
    )


# --- POST /internal/call-logs ---


def test_create_call_log_requires_hmac():
    client = _make_client(FakeSession())
    resp = client.post("/api/v1/internal/call-logs", json={"request_id": "r1", "user_id": 1, "model_name": "gpt-4"})
    assert resp.status_code == 403


def test_create_call_log_rejects_admin_caller():
    client = _make_client(FakeSession())
    path = "/api/v1/internal/call-logs"
    body = {"request_id": "r1", "user_id": 1, "model_name": "gpt-4"}
    resp = client.post(
        path,
        json=body,
        headers=_admin_headers("POST", path, json_body=body),
    )
    assert resp.status_code == 403


def test_create_call_log_success():
    session = FakeSession()
    client = _make_client(session)
    path = "/api/v1/internal/call-logs"
    body = {"request_id": "req-001", "user_id": 42, "model_name": "auto", "is_stream": True, "status": 0}
    resp = client.post(
        path,
        json=body,
        headers=_router_headers("POST", path, json_body=body),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == "req-001"
    assert "id" in data


def test_create_call_log_idempotent():
    session = FakeSession()
    existing = SimpleNamespace(id=99999, request_id="req-dup")
    session._store["req-dup"] = existing
    client = _make_client(session)
    path = "/api/v1/internal/call-logs"
    body = {"request_id": "req-dup", "user_id": 1, "model_name": "gpt-4"}
    resp = client.post(
        path,
        json=body,
        headers=_router_headers("POST", path, json_body=body),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 99999


# --- PATCH /internal/call-logs/{request_id} ---


def test_update_call_log_requires_hmac():
    client = _make_client(FakeSession())
    resp = client.patch("/api/v1/internal/call-logs/req-001", json={"status": 1})
    assert resp.status_code == 403


def test_update_call_log_not_found():
    session = FakeSession()
    client = _make_client(session)
    path = "/api/v1/internal/call-logs/nonexistent"
    body = {"status": 1}
    resp = client.patch(
        path,
        json=body,
        headers=_router_headers("PATCH", path, json_body=body),
    )
    assert resp.status_code == 404


def test_update_call_log_success():
    session = FakeSession()
    log = SimpleNamespace(
        id=100, request_id="req-upd", status=0, selected_model=None,
        provider_slug=None, upstream_model=None, config_version=None,
        config_source=None, inference_config_version=None,
        inference_config_source=None, routing_tier=None, score_source=None,
        router_trace_id=None, inference_error_code=None,
        prompt_tokens=0, completion_tokens=0, cached_tokens=0, total_tokens=0,
        duration_ms=None, error_code=None, error_msg=None, cost=None,
        cost_detail=None, updated_at=None,
    )
    session._store["req-upd"] = log
    client = _make_client(session)
    path = "/api/v1/internal/call-logs/req-upd"
    body = {"status": 1, "selected_model": "gpt-4", "duration_ms": 150}
    resp = client.patch(
        path,
        json=body,
        headers=_router_headers("PATCH", path, json_body=body),
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert log.status == 1
    assert log.selected_model == "gpt-4"
    assert log.duration_ms == 150


def test_update_call_log_truncates_error_msg():
    session = FakeSession()
    log = SimpleNamespace(
        id=101, request_id="req-trunc", status=0, selected_model=None,
        provider_slug=None, upstream_model=None, config_version=None,
        config_source=None, inference_config_version=None,
        inference_config_source=None, routing_tier=None, score_source=None,
        router_trace_id=None, inference_error_code=None,
        prompt_tokens=0, completion_tokens=0, cached_tokens=0, total_tokens=0,
        duration_ms=None, error_code=None, error_msg=None, cost=None,
        cost_detail=None, updated_at=None,
    )
    session._store["req-trunc"] = log
    client = _make_client(session)
    path = "/api/v1/internal/call-logs/req-trunc"
    long_msg = "x" * 800
    body = {"status": 2, "error_msg": long_msg}
    resp = client.patch(
        path,
        json=body,
        headers=_router_headers("PATCH", path, json_body=body),
    )
    assert resp.status_code == 200
    assert len(log.error_msg) == 512


# --- GET /internal/usage/logs allows admin-service (read) ---


def test_usage_logs_read_allows_admin_caller():
    session = FakeSession()
    client = _make_client(session)
    path = "/api/v1/internal/usage/logs"
    resp = client.get(
        path,
        headers=_admin_headers("GET", path),
    )
    # Should not be 403 — admin-service can read
    assert resp.status_code != 403
