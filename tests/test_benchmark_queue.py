# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from testing_service.api.dependencies import get_current_admin, get_db_session
from testing_service.api.v1.endpoints import benchmark


def _build_app(db_session=None) -> FastAPI:
    app = FastAPI()
    app.include_router(benchmark.router, prefix="/api/v1")

    async def _fake_db():
        yield db_session if db_session is not None else object()

    async def _fake_admin():
        return SimpleNamespace(id=99, uid=1001, role="admin", status=1)

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_current_admin] = _fake_admin
    return app


def test_trigger_probe_all_enqueues_job(monkeypatch):
    events = []
    db_session = SimpleNamespace(commit=AsyncMock(side_effect=lambda: events.append("commit")))
    app = _build_app(db_session=db_session)
    client = TestClient(app)

    monkeypatch.setattr(benchmark, "get_settings", lambda: SimpleNamespace(probe_enabled=True, probe_region="cn-east"))
    monkeypatch.setattr(
        benchmark.OfferingService,
        "list_all_active",
        AsyncMock(return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)]),
    )
    monkeypatch.setattr(
        benchmark.BenchmarkJobService,
        "create",
        AsyncMock(
            return_value=SimpleNamespace(
                job_id="full_job_1",
                job_type="full",
                status="queued",
            )
        ),
    )
    monkeypatch.setattr(
        benchmark,
        "enqueue_full_benchmark_job",
        AsyncMock(side_effect=lambda job_id: events.append(f"enqueue:{job_id}")),
    )

    response = client.post("/api/v1/benchmark/probe/trigger")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["job_id"] == "full_job_1"
    assert payload["queued_count"] == 2
    benchmark.enqueue_full_benchmark_job.assert_awaited_once_with("full_job_1")
    assert events == ["commit", "enqueue:full_job_1"]


def test_trigger_probe_all_returns_503_when_queue_unavailable(monkeypatch):
    events = []
    db_session = SimpleNamespace(commit=AsyncMock(side_effect=lambda: events.append("commit")))
    app = _build_app(db_session=db_session)
    client = TestClient(app)

    monkeypatch.setattr(benchmark, "get_settings", lambda: SimpleNamespace(probe_enabled=True, probe_region="cn-east"))
    monkeypatch.setattr(
        benchmark.OfferingService,
        "list_all_active",
        AsyncMock(return_value=[SimpleNamespace(id=1)]),
    )
    monkeypatch.setattr(
        benchmark.BenchmarkJobService,
        "create",
        AsyncMock(return_value=SimpleNamespace(job_id="full_job_2", job_type="full", status="queued")),
    )
    monkeypatch.setattr(
        benchmark.BenchmarkJobService,
        "mark_failed",
        AsyncMock(side_effect=lambda *_args, **_kwargs: events.append("mark_failed")),
    )
    monkeypatch.setattr(
        benchmark,
        "enqueue_full_benchmark_job",
        AsyncMock(side_effect=benchmark.BenchmarkQueueUnavailableError("redis down")),
    )

    response = client.post("/api/v1/benchmark/probe/trigger")
    assert response.status_code == 503
    assert "benchmark queue unavailable" in response.json()["detail"]
    assert events == ["commit", "mark_failed", "commit"]


def test_trigger_probe_one_enqueues_single_job(monkeypatch):
    events = []
    db_session = SimpleNamespace(commit=AsyncMock(side_effect=lambda: events.append("commit")))
    app = _build_app(db_session=db_session)
    client = TestClient(app)

    monkeypatch.setattr(benchmark, "get_settings", lambda: SimpleNamespace(probe_enabled=True, probe_region="cn-east"))
    monkeypatch.setattr(
        benchmark.OfferingService,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=123, is_active=True)),
    )
    monkeypatch.setattr(
        benchmark.BenchmarkJobService,
        "create",
        AsyncMock(return_value=SimpleNamespace(job_id="single_job_1", job_type="single", status="queued")),
    )
    monkeypatch.setattr(
        benchmark,
        "enqueue_single_benchmark_job",
        AsyncMock(side_effect=lambda job_id, offering_id, admin_id: events.append(f"enqueue:{job_id}:{offering_id}:{admin_id}")),
    )

    response = client.post("/api/v1/benchmark/probe/123")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["job_id"] == "single_job_1"
    assert payload["queued_count"] == 1
    benchmark.enqueue_single_benchmark_job.assert_awaited_once_with("single_job_1", 123, 99)
    assert events == ["commit", "enqueue:single_job_1:123:99"]


def test_get_probe_audits_returns_admin_only_records(monkeypatch):
    app = _build_app()
    client = TestClient(app)

    monkeypatch.setattr(
        benchmark.AdminProbeAuditService,
        "list",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    job_id="single_job_1",
                    offering_id=12,
                    model_id=3,
                    provider_id=4,
                    triggered_by_admin_id=99,
                    status="completed",
                    success=True,
                    error_code=None,
                    ttft_ms=120,
                    e2e_latency_ms=640,
                    throughput_tps=18.5,
                    prompt_tokens=10,
                    output_tokens=24,
                    probe_region="cn-east",
                    started_at=None,
                    finished_at=None,
                    created_at="2026-03-12T10:00:00",
                )
            ]
        ),
    )

    response = client.get("/api/v1/benchmark/probe-audits", params={"offering_id": 12})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["job_id"] == "single_job_1"
