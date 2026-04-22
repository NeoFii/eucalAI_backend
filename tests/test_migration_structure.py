from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERVICE_DIRS = (
    "admin_service",
    "user_service",
)


def test_service_local_migration_directories_exist():
    for service_dir in SERVICE_DIRS:
        root = ROOT / "migrations" / service_dir
        assert (root / "env.py").exists(), service_dir
        assert (root / "script.py.mako").exists(), service_dir
        assert (root / "versions" / "__init__.py").exists(), service_dir
        baseline_files = list((root / "versions").glob("*_baseline.py"))
        assert baseline_files, service_dir


def test_migration_cli_declares_all_services():
    from scripts.migrate import SERVICE_CONFIGS

    assert set(SERVICE_CONFIGS) == {"admin-service", "user-service"}

    source = (ROOT / "scripts" / "migrate.py").read_text(encoding="utf-8")
    assert "command.upgrade" in source
    assert "command.revision" in source
    assert "load_project_dotenv()" in source


def test_pyproject_exposes_migrate_script_and_alembic_dependency():
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"alembic>=' in source
    assert 'migrate = "scripts.migrate:main"' in source
    assert 'bootstrap-databases = "scripts.bootstrap_service_databases:main"' in source
    assert 'check-env = "scripts.check_service_environment:main"' in source


def test_bootstrap_database_script_exists_and_declares_all_services():
    source = (ROOT / "scripts" / "bootstrap_service_databases.py").read_text(encoding="utf-8")

    assert "SERVICE_CONFIGS" in source
    assert "args.services or list(SERVICE_CONFIGS.keys())" in source
    assert "command.upgrade" in source
    assert "missing service database URLs" in source
    assert "load_project_dotenv()" in source


def test_migration_envs_require_service_specific_database_urls():
    """Per-service env.py is a thin proxy; canonical behavior lives in _env_shared.py
    and database_env wiring lives in scripts/migrate.py::SERVICE_CONFIGS."""

    shared_env = (ROOT / "migrations" / "_env_shared.py").read_text(encoding="utf-8")
    assert "run_env" in shared_env
    assert 'database_env' in shared_env
    assert 'os.getenv(database_env' in shared_env
    assert 'os.getenv("DATABASE_URL"' not in shared_env

    from scripts.migrate import SERVICE_CONFIGS

    for env_name in (
        "ADMIN_DATABASE_URL",
        "USER_DATABASE_URL",
    ):
        assert any(config.database_env == env_name for config in SERVICE_CONFIGS.values()), env_name

    for service_dir in SERVICE_DIRS:
        env_source = (ROOT / "migrations" / service_dir / "env.py").read_text(encoding="utf-8")
        assert "from migrations._env_shared import run_env" in env_source, service_dir
        assert "run_env()" in env_source, service_dir
        assert 'os.getenv("DATABASE_URL"' not in env_source


def test_shared_env_module_is_single_source_of_truth():
    """Ensure _env_shared.py carries the full Alembic online/offline logic so
    that per-service env.py files stay minimal proxies."""

    shared = (ROOT / "migrations" / "_env_shared.py").read_text(encoding="utf-8")
    for marker in (
        "context.is_offline_mode",
        "async_engine_from_config",
        "target_metadata",
        "service_package",
        "compare_type=True",
    ):
        assert marker in shared, marker


def test_shared_async_migration_env_commits_version_table_updates():
    """MySQL DDL autocommits, but Alembic's version-table UPDATE still needs
    the SQLAlchemy async connection transaction committed explicitly."""

    shared = (ROOT / "migrations" / "_env_shared.py").read_text(encoding="utf-8")

    assert "await connection.run_sync(do_run_migrations)" in shared
    assert "await connection.commit()" in shared


def test_each_service_has_independent_revision_chain():
    """Every service owns its own linear revision history under versions/."""

    for service_dir in SERVICE_DIRS:
        versions_dir = ROOT / "migrations" / service_dir / "versions"
        revisions = [p for p in versions_dir.glob("*.py") if p.name != "__init__.py"]
        assert revisions, service_dir
        for path in revisions:
            text = path.read_text(encoding="utf-8")
            # each revision declares its own revision identifier, belongs to one chain
            assert "revision" in text, path.name
            assert "down_revision" in text, path.name


def test_readme_mentions_service_local_migration_workflow():
    source = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run migrate --service admin-service upgrade head" in source
    assert "uv run bootstrap-databases" in source


def test_deploy_and_env_examples_use_service_database_urls_only():
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "ADMIN_DATABASE_URL",
        "USER_DATABASE_URL",
    ):
        assert key in compose
        assert key in env_example

    removed_database_env = "TESTING" + "_DATABASE_URL"
    assert removed_database_env not in compose
    assert removed_database_env not in env_example

    assert "\n      DATABASE_URL:" not in compose
    assert "\nDATABASE_URL=" not in env_example
    assert "AUTO_INIT_DB" not in compose
    assert "AUTO_INIT_DB" not in env_example


def test_start_services_uses_environment_preflight():
    source = (ROOT / "scripts" / "start_services.py").read_text(encoding="utf-8")

    assert "validate_environment(selected)" in source
    assert "--skip-preflight" in source
    assert "load_project_dotenv()" in source


def test_runtime_schema_management_is_alembic_only():
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    migration_readme = (ROOT / "migrations" / "README.md").read_text(encoding="utf-8")

    assert "uv run bootstrap-databases" in root_readme
    assert "skip-init-db" not in root_readme
    assert "AUTO_INIT_DB" not in root_readme
    assert "唯一 schema 真理" in migration_readme


def test_user_api_key_soft_delete_migration_creates_deleted_at_index():
    source = (
        ROOT
        / "migrations"
        / "user_service"
        / "versions"
        / "20260420_11_add_deleted_at_to_user_api_keys.py"
    ).read_text(encoding="utf-8")

    assert "deleted_at" in source
    assert "CREATE INDEX" in source or "op.create_index" in source
    assert "DROP INDEX" in source or "op.drop_index" in source
