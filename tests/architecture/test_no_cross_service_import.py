from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
SERVICE_NAMES = (
    "admin_service", "user_service",
    "router_service", "inference_service",
)


def _service_files(service_name: str) -> list[Path]:
    return [
        path
        for path in (SRC_ROOT / service_name).rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def test_services_do_not_import_other_service_models_or_services_directly():
    for service_name in SERVICE_NAMES:
        other_services = [name for name in SERVICE_NAMES if name != service_name]
        for path in _service_files(service_name):
            source = path.read_text(encoding="utf-8")
            for other in other_services:
                assert (
                    f"from {other}.models" not in source
                ), f"{path} still imports {other}.models directly"
                assert (
                    f"import {other}.models" not in source
                ), f"{path} still imports {other}.models directly"
                assert (
                    f"from {other}.services" not in source
                ), f"{path} still imports {other}.services directly"
                assert (
                    f"import {other}.services" not in source
                ), f"{path} still imports {other}.services directly"


def test_legacy_internal_client_files_are_removed():
    removed_paths = [
        SRC_ROOT / "admin_service" / "services" / "identity_client.py",
        SRC_ROOT / "router_service" / "services" / "identity_client.py",
        SRC_ROOT / "user_service" / "services" / "admin_client.py",
    ]

    for path in removed_paths:
        assert not path.exists(), f"{path} should be removed"


def test_service_local_pagination_shims_are_removed():
    user_common = (SRC_ROOT / "user_service" / "schemas" / "common.py").read_text(encoding="utf-8")
    admin_user_schemas = (SRC_ROOT / "admin_service" / "schemas" / "admin_user.py").read_text(
        encoding="utf-8"
    )
    admin_audit_schemas = (SRC_ROOT / "admin_service" / "schemas" / "audit_log.py").read_text(
        encoding="utf-8"
    )
    admin_invitation_schemas = (
        SRC_ROOT / "admin_service" / "schemas" / "invitation.py"
    ).read_text(encoding="utf-8")

    assert "class ListResponse" not in user_common
    assert "class AdminListResponseData" not in admin_user_schemas
    assert "class AdminAuditLogListData" not in admin_audit_schemas
    assert "class InvitationCodeListResponseData" not in admin_invitation_schemas
    assert "PaginatedResponse" in admin_user_schemas
    assert "PaginatedResponse" in admin_audit_schemas
    assert "PaginatedResponse" in admin_invitation_schemas


def test_remaining_service_and_endpoint_database_queries_are_in_repositories():
    checked_paths = [
        SRC_ROOT / "admin_service" / "api" / "v1" / "endpoints" / "internal.py",
        SRC_ROOT / "admin_service" / "services" / "bootstrap_service.py",
        SRC_ROOT / "user_service" / "api" / "v1" / "endpoints" / "internal.py",
    ]

    for path in checked_paths:
        source = path.read_text(encoding="utf-8")
        assert "await db.execute(" not in source, f"{path} still executes SQL directly"
        assert "select(" not in source, f"{path} still builds SQL directly"


def test_gateway_implementations_share_base_gateway():
    expected_markers = {
        SRC_ROOT / "user_service" / "gateway.py": [
            "class AdminInvitationGatewayInterface",
            "class AdminInvitationGateway(BaseGateway, AdminInvitationGatewayInterface):",
        ],
        SRC_ROOT / "router_service" / "gateway.py": [
            "from common.gateway.base import BaseGateway",
            "class UserIdentityGateway(BaseGateway):",
        ],
    }

    for path, markers in expected_markers.items():
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, f"{path} is missing {marker}"
