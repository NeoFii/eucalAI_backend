from pathlib import Path


ROOT = Path(r"F:\Eucal_AI\backend")
SERVICE_DIRS = (
    "admin_service",
    "user_service",
    "router_service",
    "content_service",
    "testing_service",
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
    source = (ROOT / "scripts" / "migrate.py").read_text(encoding="utf-8")

    for service in (
        "admin-service",
        "user-service",
        "router-service",
        "content-service",
        "testing-service",
    ):
        assert service in source

    assert "command.upgrade" in source
    assert "command.revision" in source
    assert "ADMIN_DATABASE_URL" in source
    assert "TESTING_DATABASE_URL" in source
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
    for service_dir, env_name in (
        ("admin_service", "ADMIN_DATABASE_URL"),
        ("user_service", "USER_DATABASE_URL"),
        ("router_service", "ROUTER_DATABASE_URL"),
        ("content_service", "CONTENT_DATABASE_URL"),
        ("testing_service", "TESTING_DATABASE_URL"),
    ):
        source = (ROOT / "migrations" / service_dir / "env.py").read_text(encoding="utf-8")
        assert env_name in source
        assert 'os.getenv("DATABASE_URL"' not in source


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
        "ROUTER_DATABASE_URL",
        "CONTENT_DATABASE_URL",
        "TESTING_DATABASE_URL",
    ):
        assert key in compose
        assert key in env_example

    assert "\n      DATABASE_URL:" not in compose
    assert "\nDATABASE_URL=" not in env_example


def test_start_services_uses_environment_preflight():
    source = (ROOT / "scripts" / "start_services.py").read_text(encoding="utf-8")

    assert "validate_environment(selected)" in source
    assert "--skip-preflight" in source
    assert "load_project_dotenv()" in source
