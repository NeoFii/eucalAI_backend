from __future__ import annotations

import logging
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def test_backend_app_runtime_does_not_call_init_db():
    source = (ROOT / "src" / "backend_app" / "lifecycle.py").read_text(encoding="utf-8")
    assert "init_db(" not in source


def test_standalone_services_do_not_call_init_db():
    admin_main = (ROOT / "src" / "admin_service" / "main.py").read_text(encoding="utf-8")
    testing_main = (ROOT / "src" / "testing_service" / "main.py").read_text(encoding="utf-8")
    assert "init_db(" not in admin_main
    assert "init_db(" not in testing_main


def test_service_db_facades_do_not_export_init_db():
    for relative_path in (
        "src/admin_service/db.py",
        "src/user_service/db.py",
        "src/testing_service/db.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "init_db =" not in source
        assert '"init_db"' not in source


def test_service_runtime_layer_does_not_create_schema_directly():
    source = (ROOT / "src" / "common" / "db" / "runtime.py").read_text(encoding="utf-8")
    assert "create_all" not in source


def test_migrate_cli_uses_committed_service_alembic_ini_files():
    from scripts.migrate import SERVICE_CONFIGS, build_alembic_config

    for service in SERVICE_CONFIGS.values():
        assert service.alembic_ini_path.name == "alembic.ini"
        assert service.alembic_ini_path.is_file()

        config = build_alembic_config(service, None)

        assert Path(config.config_file_name) == service.alembic_ini_path
        assert Path(config.get_main_option("script_location")).resolve() == service.script_location


def test_alembic_database_url_supports_percent_encoded_passwords():
    from common.db.schema_version import build_service_alembic_config

    url = "mysql+aiomysql://user:p%40ss%25word@localhost:3306/example"
    config = build_service_alembic_config("admin-service", url=url)

    assert config.get_main_option("sqlalchemy.url") == url


def test_docs_and_scripts_describe_alembic_as_only_schema_path():
    migration_readme = (ROOT / "migrations" / "README.md").read_text(encoding="utf-8")
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "schema 真理" in migration_readme
    assert "AUTO_INIT_DB" not in root_readme
    assert "skip-init-db" not in root_readme
    assert "AUTO_INIT_DB" not in compose
    assert "AUTO_INIT_DB" not in env_example


def test_docker_image_includes_migrations_for_runtime_revision_checks():
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=appuser:appuser migrations/ /app/migrations/" in dockerfile


def test_testing_worker_checks_alembic_head_before_starting_jobs():
    worker_jobs = (ROOT / "src" / "testing_service" / "benchmark" / "jobs.py").read_text(
        encoding="utf-8"
    )

    assert 'ensure_database_at_head(service_name="testing-service"' in worker_jobs
    assert worker_jobs.index("ensure_database_at_head") < worker_jobs.index("create_engine")


@pytest.mark.asyncio
async def test_ensure_database_at_head_raises_clear_error(monkeypatch):
    from common.db.schema_version import ensure_database_at_head

    async def fake_get_current_revision(*, service_name: str, url: str):
        assert service_name == "admin-service"
        assert url == "mysql+aiomysql://runtime-db"
        return "20260420_old"

    def fake_get_head_revision(service_name: str):
        assert service_name == "admin-service"
        return "20260421_head"

    monkeypatch.setattr(
        "common.db.schema_version.get_current_revision",
        fake_get_current_revision,
    )
    monkeypatch.setattr(
        "common.db.schema_version.get_head_revision",
        fake_get_head_revision,
    )

    with pytest.raises(RuntimeError) as exc_info:
        await ensure_database_at_head(
            service_name="admin-service",
            url="mysql+aiomysql://runtime-db",
        )

    message = str(exc_info.value)
    assert "admin-service database is at '20260420_old', expected '20260421_head'" in message
    assert "uv run migrate --service admin-service upgrade head" in message


@pytest.mark.asyncio
async def test_backend_app_revision_mismatch_stops_before_admin_bootstrap(monkeypatch):
    from backend_app import lifecycle

    calls: list[str] = []

    async def fake_check(*_args, **_kwargs):
        calls.append("check")
        raise RuntimeError("revision mismatch")

    async def fake_bootstrap():
        calls.append("bootstrap")
        return False

    monkeypatch.setattr(lifecycle, "ensure_database_at_head", fake_check)
    monkeypatch.setattr(
        "backend_app.lifecycle.AdminBootstrapService.ensure_super_admin",
        fake_bootstrap,
    )
    monkeypatch.setattr("backend_app.lifecycle.configure_snowflake", lambda **_kwargs: None)
    monkeypatch.setattr("backend_app.lifecycle.admin_db.create_engine", lambda **_kwargs: None)
    monkeypatch.setattr("backend_app.lifecycle.user_db.create_engine", lambda **_kwargs: None)
    monkeypatch.setattr("backend_app.lifecycle.testing_db.create_engine", lambda **_kwargs: None)
    monkeypatch.setattr("backend_app.lifecycle.admin_db.init_session_factory", lambda: None)
    monkeypatch.setattr("backend_app.lifecycle.user_db.init_session_factory", lambda: None)
    monkeypatch.setattr("backend_app.lifecycle.testing_db.init_session_factory", lambda: None)

    manager = lifecycle.build_lifecycle_manager(logger=logging.getLogger("test"))

    with pytest.raises(RuntimeError, match="revision mismatch"):
        await manager.startup()

    assert calls == ["check"]
