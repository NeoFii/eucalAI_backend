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
        "schema": ROOT / "scripts" / "sql" / "admin_schema.sql",
        "tables": [
            "admin_users",
            "admin_audit_logs",
            "invitation_codes",
            "model_vendors",
            "model_categories",
            "supported_models",
            "supported_model_category_map",
        ],
        "views": [],
        "base": admin_db.Base,
    },
    "user": {
        "schema": ROOT / "scripts" / "sql" / "user_schema.sql",
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
            "invitation_release_outbox",
        ],
        "views": [],
        "base": user_db.Base,
    },
}


def _parse_schema(schema_path: Path) -> tuple[dict[str, list[str]], set[str]]:
    source = schema_path.read_text(encoding="utf-8")
    tables = {}
    for match in CREATE_TABLE_PATTERN.finditer(source):
        body = match.group("body")
        columns = [line.split("`")[1] for line in body.splitlines() if line.strip().startswith("`")]
        tables[match.group("name")] = columns

    views = {match.group("name") for match in CREATE_VIEW_PATTERN.finditer(source)}
    return tables, views


def test_owned_schema_files_match_service_local_metadata_columns():
    for service, config in OWNED_SCHEMAS.items():
        schema_tables, schema_views = _parse_schema(config["schema"])

        assert set(schema_tables) == set(config["tables"]), service
        assert schema_views == set(config["views"]), service

        metadata = config["base"].metadata
        assert set(metadata.tables.keys()) == set(config["tables"]) | set(config["views"]), service

        for table_name in config["tables"]:
            orm_columns = set(metadata.tables[table_name].columns.keys())
            sql_columns = set(schema_tables[table_name])
            assert orm_columns == sql_columns, f"{service}:{table_name}"
