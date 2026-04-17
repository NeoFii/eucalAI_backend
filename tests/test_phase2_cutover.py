import json
from pathlib import Path

import pytest

pytest.skip(
    "phase2 cutover manifest was pinned to the legacy router layout; deprecated "
    "together with router key/billing until reintroduced.",
    allow_module_level=True,
)

from scripts.migrate import SERVICE_CONFIGS


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "migrations" / "cutover_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_cutover_manifest_declares_all_services_in_expected_order():
    manifest = load_manifest()

    assert manifest["execution_order"] == [
        "router-service",
        "testing-service",
        "admin-service",
        "user-service",
        "content-service",
    ]

    services = {entry["service"] for entry in manifest["services"]}
    assert services == set(manifest["execution_order"])


def test_cutover_manifest_entries_are_consistent():
    manifest = load_manifest()
    entries = manifest["services"]

    for expected_order, entry in enumerate(entries, start=1):
        assert entry["order"] == expected_order
        assert entry["service"] == manifest["execution_order"][expected_order - 1]
        assert entry["database_env"].endswith("_DATABASE_URL")
        assert entry["migration_namespace"].startswith("migrations/")
        assert entry["schema_snapshot"].startswith("scripts/sql/")
        assert entry["owned_tables"]
        assert "preconditions" in entry
        assert "post_cutover_checks" in entry


def test_cutover_manifest_matches_migration_service_config():
    manifest = load_manifest()

    for entry in manifest["services"]:
        service_config = SERVICE_CONFIGS[entry["service"]]
        assert entry["database_env"] == service_config.database_env
        assert entry["migration_namespace"] == f"migrations/{service_config.package}"


def test_phase2_cutover_script_and_docs_are_registered():
    source = (ROOT / "scripts" / "phase2_cutover.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "phase2-cutover.md").read_text(encoding="utf-8")

    assert "cutover_manifest.json" in source
    assert "--check-env" in source
    assert "load_project_dotenv()" in source
    assert 'phase2-cutover = "scripts.phase2_cutover:main"' in pyproject
    assert "docs/phase2-cutover.md" in readme
    assert "uv run phase2-cutover" in doc
    assert "router-service" in doc
    assert "content-service" in doc
