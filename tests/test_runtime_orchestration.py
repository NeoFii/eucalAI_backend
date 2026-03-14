from pathlib import Path

ROOT = Path(r"F:\Eucal_AI\backend")


def test_compose_uses_readiness_checks_and_explicit_scheduler_role():
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'scripts/runtime_probe.py", "http-ready"' in compose
    assert "/health" not in compose
    assert "testing-worker:" in compose
    assert 'scripts/runtime_probe.py", "worker-ready"' in compose
    assert "testing-scheduler:" in compose
    assert 'profiles: ["scheduler"]' in compose
    assert '"--port", "8012"' in compose


def test_dockerfile_relies_on_compose_healthchecks():
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK" not in dockerfile
    assert "EXPOSE 8000 8001 8002 8003 8004 8012" in dockerfile


def test_start_services_supports_scheduler_role_and_readiness_probes():
    source = (ROOT / "scripts" / "start_services.py").read_text(encoding="utf-8")

    assert '"testing-scheduler"' in source
    assert "DEFAULT_SERVICES" in source
    assert 'path="/ready"' in source
    assert '"PROBE_SCHEDULER_ENABLED": "true"' in source
    assert '"PROBE_SCHEDULER_ENABLED": "false"' in source


def test_env_validation_knows_scheduler_role():
    source = (ROOT / "scripts" / "check_service_environment.py").read_text(encoding="utf-8")

    assert '"testing-scheduler": "TESTING_DATABASE_URL"' in source


def test_operations_docs_cover_compose_runtime_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "phase4-operations.md").read_text(encoding="utf-8")

    assert "testing-scheduler" in readme
    assert "/ready" in readme
    assert "--profile scheduler" in readme
    assert "Compose Orchestration" in operations
    assert "dependency probe" in operations
