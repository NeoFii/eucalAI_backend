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
