import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PATTERN = re.compile(r"REFERENCES `(?P<table>[^`]+)`")
SERVICE_OWNED_OBJECTS = {
    "admin": {
        "admin_users",
        "admin_audit_logs",
        "invitation_codes",
        "model_vendors",
        "model_categories",
        "supported_models",
        "supported_model_category_map",
        "routing_configs",
        "provider_credentials",
    },
    "user": {
        "users",
        "user_sessions",
        "email_verification_codes",
        "user_api_keys",
        "voucher_redemption_codes",
        "balance_transactions",
        "topup_orders",
        "api_call_logs",
        "usage_stats",
        "invitation_release_outbox",
    },
}

SNAPSHOT_PATHS = {
    "admin": ROOT / "scripts" / "sql" / "admin_schema.sql",
    "user": ROOT / "scripts" / "sql" / "user_schema.sql",
}


def _read_all_snapshots() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SNAPSHOT_PATHS.values())


def test_schema_ownership_docs_and_files_exist():
    ownership_doc = (ROOT / "docs" / "schema-ownership.md").read_text(encoding="utf-8")

    assert "admin_schema.sql" in ownership_doc
    assert "admin_users" in ownership_doc
    assert "users" in ownership_doc
    assert "user_api_keys" in ownership_doc
    assert "bootstrap-databases" in ownership_doc


def test_snapshots_exist_and_exclude_db_less_services():
    source = _read_all_snapshots()

    assert "CREATE TABLE IF NOT EXISTS `admin_users`" in source
    assert "CREATE TABLE IF NOT EXISTS `users`" in source
    assert "router_service" not in source
    assert "inference_service" not in source


def test_redundant_sql_files_have_been_removed():
    redundant_paths = [
        ROOT / "scripts" / "sql" / "init_owned_tables.sql",
        ROOT / "scripts" / "sql" / "models.sql",
        ROOT / "scripts" / "sql" / "admin_migrations.sql",
        ROOT / "scripts" / "sql" / "user_migrations.sql",
        ROOT / "scripts" / "sql" / "router_migrations.sql",
        ROOT / "scripts" / "sql" / "testing_migrations.sql",
        ROOT / "scripts" / "sql" / "apply_owned_migrations.sql",
        ROOT / "scripts" / "sql" / "router_migration.sql",
        ROOT / "scripts" / "sql" / "router_key_reveal_migration.sql",
        ROOT / "scripts" / "sql" / "benchmark_queue_migration.sql",
        ROOT / "scripts" / "sql" / "router_schema.sql",
        ROOT / "scripts" / "sql" / "testing_schema.sql",
        ROOT / "scripts" / "sql" / "migrations",
    ]

    assert all(not path.exists() for path in redundant_paths)


def test_sql_snapshots_only_reference_service_owned_tables():
    source = _read_all_snapshots()
    references = {match.group("table") for match in REFERENCE_PATTERN.finditer(source)}
    allowed = set().union(*SERVICE_OWNED_OBJECTS.values())

    assert references <= allowed, f"cross-service references found: {sorted(references - allowed)}"


def test_snapshot_contains_all_owned_tables():
    source = _read_all_snapshots()

    for owned_objects in SERVICE_OWNED_OBJECTS.values():
        for table_name in owned_objects:
            assert f"CREATE TABLE IF NOT EXISTS `{table_name}`" in source, table_name


def test_readme_uses_new_canonical_bootstrap_entrypoint():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run bootstrap-databases" in readme
    assert "scripts/sql/" in readme
