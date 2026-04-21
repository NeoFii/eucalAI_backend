"""Admin-service overview refactor boundaries."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
ADMIN_ROOT = SRC_ROOT / "admin_service"


def _source(path: str) -> str:
    return (ADMIN_ROOT / path).read_text(encoding="utf-8")


def test_admin_schema_modules_are_split_and_export_real_types():
    from admin_service.schemas import AdminLoginRequest, GenerateInvitationCodeRequest
    from admin_service.schemas.admin_user import CreateAdminRequest
    from admin_service.schemas.audit_log import AdminAuditLogItem
    from admin_service.schemas.auth import AdminLoginRequest as AuthLoginRequest
    from admin_service.schemas.invitation import (
        GenerateInvitationCodeRequest as InvitationGenerateRequest,
    )

    assert AdminLoginRequest is AuthLoginRequest
    assert GenerateInvitationCodeRequest is InvitationGenerateRequest
    assert AuthLoginRequest.__module__ == "admin_service.schemas.auth"
    assert InvitationGenerateRequest.__module__ == "admin_service.schemas.invitation"
    assert CreateAdminRequest.__module__ == "admin_service.schemas.admin_user"
    assert AdminAuditLogItem.__module__ == "admin_service.schemas.audit_log"


def test_admin_gateway_replaces_legacy_identity_client():
    from admin_service.gateway import UserStatsGateway

    assert UserStatsGateway is not None
    assert not (ADMIN_ROOT / "services" / "identity_client.py").exists()


def test_admin_policy_module_owns_authorization_guards():
    from admin_service.policies import require_active_admin, require_super_admin

    assert require_active_admin is not None
    assert require_super_admin is not None
    assert "AdminPermissionDeniedException" not in _source("dependencies.py")


def test_admin_services_use_repositories_for_database_queries():
    for path in [
        "services/auth_service.py",
        "services/management_service.py",
        "services/invitation_service.py",
        "services/audit_service.py",
    ]:
        source = _source(path)
        assert "admin_service.repositories" in source
        assert "from sqlalchemy import" not in source
        assert "select(" not in source
        assert "db.execute(" not in source


@pytest.mark.asyncio
async def test_user_stats_gateway_uses_internal_helper(monkeypatch):
    from admin_service.gateway import UserStatsGateway

    captured = {}

    async def fake_get_internal_json(**kwargs):
        captured.update(kwargs)
        return {"total_users": 42}

    monkeypatch.setattr("admin_service.gateway.get_internal_json", fake_get_internal_json)

    total = await UserStatsGateway().fetch_total_users()

    assert total == 42
    assert captured["target_service"] == "user-service"
    assert captured["path"] == "/api/v1/internal/stats/users"
