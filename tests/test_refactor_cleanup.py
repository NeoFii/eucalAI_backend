from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USER_SERVICE_ROOT = ROOT / "src" / "user_service"
ADMIN_SERVICE_ROOT = ROOT / "src" / "admin_service"

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"


def test_user_service_package_exposes_current_public_contract():
    from user_service import AdminInvitationGateway, require_active_user

    assert AdminInvitationGateway.__module__ == "user_service.gateway"
    assert require_active_user.__module__ == "user_service.policies"


def test_service_package_roots_use_direct_public_exports():
    user_init = (USER_SERVICE_ROOT / "__init__.py").read_text(encoding="utf-8")
    admin_init = (ADMIN_SERVICE_ROOT / "__init__.py").read_text(encoding="utf-8")

    assert '"AdminInvitationGateway"' in user_init
    assert '"require_active_user"' in user_init
    assert '"UserStatsGateway"' in admin_init
    assert '"require_super_admin"' in admin_init


def test_user_schema_package_is_final_public_export_surface():
    source = (USER_SERVICE_ROOT / "schemas" / "__init__.py").read_text(encoding="utf-8")

    assert "Compatibility schema package" not in source


def test_user_service_tree_no_longer_references_legacy_schema_shim():
    assert not (USER_SERVICE_ROOT / "schemas_legacy.py").exists()

    sources = [
        path
        for path in USER_SERVICE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert "schemas_legacy" not in source, f"{path} still references schemas_legacy"


def test_completed_service_packages_do_not_keep_removed_legacy_client_files():
    removed_paths = [
        USER_SERVICE_ROOT / "services" / "content_client.py",
        USER_SERVICE_ROOT / "services" / "admin_client.py",
        ADMIN_SERVICE_ROOT / "services" / "identity_client.py",
    ]

    for path in removed_paths:
        assert not path.exists(), f"{path} should be removed"


def test_admin_service_config_no_longer_defines_content_service_url():
    checked_paths = [
        ADMIN_SERVICE_ROOT / "config.py",
        ROOT / "deploy" / "docker-compose.yml",
    ]

    for path in checked_paths:
        source = path.read_text(encoding="utf-8")
        assert "CONTENT_SERVICE_URL" not in source, f"{path} still defines CONTENT_SERVICE_URL"


def test_runtime_schema_creation_paths_are_removed_from_public_files():
    checked_paths = [
        ROOT / "src" / "backend_app" / "lifecycle.py",
        ROOT / "src" / "admin_service" / "main.py",
        ROOT / "src" / "admin_service" / "bootstrap_superadmin.py",
        ROOT / "README.md",
        ROOT / ".env.example",
        ROOT / "deploy" / "docker-compose.yml",
    ]

    for path in checked_paths:
        source = path.read_text(encoding="utf-8")
        assert "AUTO_INIT_DB" not in source, f"{path} still advertises AUTO_INIT_DB"
        assert "skip-init-db" not in source, f"{path} still advertises skip-init-db"


def test_project_structure_doc_matches_refactored_layout():
    source = (ROOT / "docs" / "PROJECT_STRUCTURE.md").read_text(encoding="utf-8")
    stale_markers = [
        "src/admin_service/schemas.py",
        "src/user_service/schemas.py",
        "src/router_service/schemas.py",
        "src/admin_service/services/identity_client.py",
        "src/user_service/services/admin_client.py",
    ]

    for marker in stale_markers:
        assert marker not in source, f"PROJECT_STRUCTURE.md still documents {marker}"
