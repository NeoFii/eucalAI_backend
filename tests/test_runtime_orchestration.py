from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_readiness_checks_for_active_http_services_only():
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    removed_worker = "testing" + "-worker"
    removed_scheduler = "testing" + "-scheduler"

    assert 'scripts/runtime_probe.py", "http-ready"' in compose
    assert "/health" not in compose
    assert removed_worker + ":" not in compose
    assert 'scripts/runtime_probe.py", "worker-ready"' not in compose
    assert removed_scheduler + ":" not in compose
    assert 'profiles: ["scheduler"]' not in compose
    assert '"--port", "8012"' not in compose


def test_dockerfile_relies_on_compose_healthchecks():
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK" not in dockerfile
    assert "EXPOSE 8000 8001 8003 8004" in dockerfile


def test_start_services_defaults_to_active_http_services_and_readiness_probes():
    source = (ROOT / "scripts" / "start_services.py").read_text(encoding="utf-8")
    removed_scheduler = "testing" + "-scheduler"
    removed_worker = "testing" + "-worker"

    assert f'"{removed_scheduler}"' not in source
    assert f'"{removed_worker}"' not in source
    assert "DEFAULT_SERVICES" in source
    assert 'path="/ready"' in source
    assert '"backend-app"' in source
    assert '"inference-service"' in source
    assert '"router-service"' in source


def test_env_validation_knows_only_active_runtime_services():
    source = (ROOT / "scripts" / "check_service_environment.py").read_text(encoding="utf-8")
    removed_scheduler = "testing" + "-scheduler"

    assert removed_scheduler not in source
    assert "DEFAULT_RUNTIME_SERVICES" in source


def test_operations_docs_cover_compose_runtime_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "phase4-operations.md").read_text(encoding="utf-8")
    removed_scheduler = "testing" + "-scheduler"

    assert removed_scheduler not in readme
    assert "/ready" in readme
    assert "Compose Orchestration" in operations
    assert "dependency probe" in operations
