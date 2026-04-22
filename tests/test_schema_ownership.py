import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PATTERN = re.compile(r"REFERENCES `(?P<table>[^`]+)`")
SERVICE_OWNED_OBJECTS = {
    "admin": {"admin_users", "admin_audit_logs", "invitation_codes"},
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


def test_schema_ownership_docs_and_files_exist():
    ownership_doc = (ROOT / "docs" / "schema-ownership.md").read_text(encoding="utf-8")

    assert "admin_schema.sql" in ownership_doc
    assert "user_schema.sql" in ownership_doc
    assert "init_tables.sql" in ownership_doc
    assert "admin_users" in ownership_doc
    assert "users" in ownership_doc
    assert "user_api_keys" in ownership_doc
    assert "bootstrap-databases" in ownership_doc


def test_init_tables_sources_service_owned_schemas_in_order():
    source = (ROOT / "scripts" / "sql" / "init_tables.sql").read_text(encoding="utf-8")

    admin_pos = source.index("SOURCE scripts/sql/admin_schema.sql;")
    user_pos = source.index("SOURCE scripts/sql/user_schema.sql;")

    assert admin_pos < user_pos
    # router-service has no database; init_tables must not source a router schema.
    assert "SOURCE scripts/sql/router_schema.sql;" not in source


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
    for service_name, owned_objects in SERVICE_OWNED_OBJECTS.items():
        source = (ROOT / "scripts" / "sql" / f"{service_name}_schema.sql").read_text(encoding="utf-8")
        references = {match.group("table") for match in REFERENCE_PATTERN.finditer(source)}
        assert references <= owned_objects, f"{service_name}: cross-service references found: {sorted(references - owned_objects)}"


def test_readme_uses_new_canonical_bootstrap_entrypoint():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run bootstrap-databases" in readme
    assert "scripts/sql/" in readme
