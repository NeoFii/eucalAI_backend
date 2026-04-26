from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_standalone_services_do_not_call_init_db():
    for relative_path in (
        "src/admin_service/main.py",
        "src/user_service/main.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "init_db(" not in source


def test_service_db_facades_do_not_export_init_db():
    for relative_path in (
        "src/admin_service/db.py",
        "src/user_service/db.py",
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
    compose = (ROOT / "deploy" / "docker-compose.backend.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "唯一" in migration_readme and "权威来源" in migration_readme
    assert "AUTO_INIT_DB" not in root_readme
    assert "skip-init-db" not in root_readme
    assert "AUTO_INIT_DB" not in compose
    assert "AUTO_INIT_DB" not in env_example


def test_docker_image_includes_migrations_for_runtime_revision_checks():
    dockerfiles = [
        (ROOT / "deploy" / "Dockerfile.admin-service").read_text(encoding="utf-8"),
        (ROOT / "deploy" / "Dockerfile.user-service").read_text(encoding="utf-8"),
        (ROOT / "deploy" / "Dockerfile.user-worker").read_text(encoding="utf-8"),
    ]

    for dockerfile in dockerfiles:
        assert "COPY --chown=appuser:appuser migrations/__init__.py" in dockerfile
        assert "COPY --chown=appuser:appuser migrations/" in dockerfile


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
