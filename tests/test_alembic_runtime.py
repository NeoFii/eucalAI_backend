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


def test_docs_and_scripts_describe_alembic_as_only_schema_path():
    migration_readme = (ROOT / "migrations" / "README.md").read_text(encoding="utf-8")
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "唯一 schema 真理" in migration_readme
    assert "AUTO_INIT_DB" not in root_readme
    assert "skip-init-db" not in root_readme
    assert "AUTO_INIT_DB" not in compose
    assert "AUTO_INIT_DB" not in env_example


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
