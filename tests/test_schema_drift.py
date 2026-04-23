import re
from pathlib import Path

import pytest

import admin_service.db as admin_db
import user_service.db as user_db

import admin_service.models  # noqa: F401
import user_service.models  # noqa: F401


ROOT = Path(__file__).resolve().parent.parent
CREATE_TABLE_PATTERN = re.compile(
    r"CREATE TABLE IF NOT EXISTS `(?P<name>[^`]+)` \((?P<body>.*?)\) ENGINE=",
    re.S,
)
CREATE_VIEW_PATTERN = re.compile(
    r"CREATE OR REPLACE VIEW `(?P<name>[^`]+)` AS",
    re.S,
)

OWNED_SCHEMAS = {
    "admin": {
        "tables": [
            "admin_users",
            "admin_audit_logs",
            "model_vendors",
            "model_categories",
            "supported_models",
            "supported_model_category_map",
            "provider_credentials",
            "routing_configs",
        ],
        "views": [],
        "base": admin_db.Base,
    },
    "user": {
        "tables": [
            "users",
            "user_sessions",
            "email_verification_codes",
            "user_api_keys",
            "voucher_redemption_codes",
            "balance_transactions",
            "topup_orders",
            "api_call_logs",
            "usage_stats",
        ],
        "views": [],
        "base": user_db.Base,
    },
}

SNAPSHOT_PATHS = [
    ROOT / "scripts" / "sql" / "admin_schema.sql",
    ROOT / "scripts" / "sql" / "user_schema.sql",
]


def _parse_schema(schema_path: Path) -> tuple[dict[str, list[str]], set[str]]:
    source = schema_path.read_text(encoding="utf-8")
    tables = {}
    for match in CREATE_TABLE_PATTERN.finditer(source):
        body = match.group("body")
        columns = [line.split("`")[1] for line in body.splitlines() if line.strip().startswith("`")]
        tables[match.group("name")] = columns

    views = {match.group("name") for match in CREATE_VIEW_PATTERN.finditer(source)}
    return tables, views


def _parse_all_snapshots() -> tuple[dict[str, list[str]], set[str]]:
    all_tables: dict[str, list[str]] = {}
    all_views: set[str] = set()
    for path in SNAPSHOT_PATHS:
        tables, views = _parse_schema(path)
        all_tables.update(tables)
        all_views.update(views)
    return all_tables, all_views


def test_owned_schema_files_match_service_local_metadata_columns():
    schema_tables, schema_views = _parse_all_snapshots()

    for service, config in OWNED_SCHEMAS.items():
        assert set(config["tables"]) <= set(schema_tables), service
        assert set(config["views"]) <= schema_views, service

        metadata = config["base"].metadata
        assert set(metadata.tables.keys()) == set(config["tables"]) | set(config["views"]), service

        for table_name in config["tables"]:
            orm_columns = set(metadata.tables[table_name].columns.keys())
            sql_columns = set(schema_tables[table_name])
            assert orm_columns == sql_columns, f"{service}:{table_name}"
