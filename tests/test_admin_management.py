from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_require_super_admin_allows_super_admin():
    from admin_service.dependencies import require_super_admin
    from admin_service.models import AdminUser

    admin = AdminUser(
        uid=1,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )

    result = await require_super_admin(admin)

    assert result is admin


@pytest.mark.asyncio
async def test_require_super_admin_rejects_normal_admin():
    from admin_service.dependencies import require_super_admin
    from admin_service.exceptions import AdminPermissionDeniedException
    from admin_service.models import AdminUser

    admin = AdminUser(
        uid=2,
        email="admin@example.com",
        password_hash="hash",
        name="Admin",
        role="admin",
        status=1,
    )

    with pytest.raises(AdminPermissionDeniedException):
        await require_super_admin(admin)


@pytest.mark.asyncio
async def test_bootstrap_service_fails_when_required_and_disabled(monkeypatch):
    from admin_service.services.bootstrap_service import AdminBootstrapService

    fake_settings = SimpleNamespace(
        BOOTSTRAP_SUPERADMIN_ENABLED=False,
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True,
        BOOTSTRAP_SUPERADMIN_EMAIL=None,
        BOOTSTRAP_SUPERADMIN_PASSWORD=None,
        BOOTSTRAP_SUPERADMIN_NAME=None,
        BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=False,
        BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=False,
    )

    @asynccontextmanager
    async def fake_db_context():
        yield object()

    async def fake_count(_db):
        return 0

    monkeypatch.setattr("admin_service.services.bootstrap_service.settings", fake_settings)
    monkeypatch.setattr("admin_service.services.bootstrap_service.get_db_context", fake_db_context)
    monkeypatch.setattr(AdminBootstrapService, "_count_active_super_admins", staticmethod(fake_count))

    with pytest.raises(RuntimeError):
        await AdminBootstrapService.ensure_super_admin()


@pytest.mark.asyncio
async def test_bootstrap_service_creates_when_missing(monkeypatch):
    from admin_service.services.bootstrap_service import AdminBootstrapService

    calls = []
    fake_admin = SimpleNamespace(
        id=1,
        uid=1001,
        email="founder@example.com",
        name="Founder",
        role="super_admin",
        status=1,
    )
    fake_settings = SimpleNamespace(
        BOOTSTRAP_SUPERADMIN_ENABLED=True,
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True,
        BOOTSTRAP_SUPERADMIN_EMAIL="founder@example.com",
        BOOTSTRAP_SUPERADMIN_PASSWORD="StrongPassword123!",
        BOOTSTRAP_SUPERADMIN_NAME="Founder",
        BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=False,
        BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=False,
    )

    @asynccontextmanager
    async def fake_db_context():
        yield object()

    async def fake_count(_db):
        return 0

    async def fake_acquire(_db):
        calls.append("acquire")
        return True

    async def fake_upsert(_db):
        calls.append("upsert")
        return fake_admin, True

    async def fake_record(_db, admin, created):
        calls.append(("record", admin.uid, created))

    async def fake_release(_db):
        calls.append("release")

    monkeypatch.setattr("admin_service.services.bootstrap_service.settings", fake_settings)
    monkeypatch.setattr("admin_service.services.bootstrap_service.get_db_context", fake_db_context)
    monkeypatch.setattr(AdminBootstrapService, "_count_active_super_admins", staticmethod(fake_count))
    monkeypatch.setattr(AdminBootstrapService, "_acquire_lock", staticmethod(fake_acquire))
    monkeypatch.setattr(AdminBootstrapService, "_upsert_bootstrap_super_admin", staticmethod(fake_upsert))
    monkeypatch.setattr(AdminBootstrapService, "_record_bootstrap_audit", staticmethod(fake_record))
    monkeypatch.setattr(AdminBootstrapService, "_release_lock", staticmethod(fake_release))

    created = await AdminBootstrapService.ensure_super_admin()

    assert created is True
    assert calls == ["acquire", "upsert", ("record", 1001, True), "release"]


@pytest.mark.asyncio
async def test_bootstrap_service_skips_when_super_admin_exists(monkeypatch):
    from admin_service.services.bootstrap_service import AdminBootstrapService

    calls = []
    fake_settings = SimpleNamespace(
        BOOTSTRAP_SUPERADMIN_ENABLED=True,
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True,
        BOOTSTRAP_SUPERADMIN_EMAIL="founder@example.com",
        BOOTSTRAP_SUPERADMIN_PASSWORD="StrongPassword123!",
        BOOTSTRAP_SUPERADMIN_NAME="Founder",
        BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=False,
        BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=False,
    )

    @asynccontextmanager
    async def fake_db_context():
        yield object()

    async def fake_count(_db):
        return 1

    async def fake_maybe_update(_db):
        calls.append("update")
        return False

    monkeypatch.setattr("admin_service.services.bootstrap_service.settings", fake_settings)
    monkeypatch.setattr("admin_service.services.bootstrap_service.get_db_context", fake_db_context)
    monkeypatch.setattr(AdminBootstrapService, "_count_active_super_admins", staticmethod(fake_count))
    monkeypatch.setattr(AdminBootstrapService, "_maybe_update_existing_super_admin", staticmethod(fake_maybe_update))

    created = await AdminBootstrapService.ensure_super_admin()

    assert created is False
    assert calls == ["update"]


def test_admin_snapshot_excludes_password_hash():
    from admin_service.models import AdminUser
    from admin_service.services.management_service import AdminManagementService

    admin = AdminUser(
        uid=123,
        email="admin@example.com",
        password_hash="secret-hash",
        name="Admin",
        role="admin",
        status=1,
    )
    admin.created_at = datetime.now()
    admin.updated_at = datetime.now()

    snapshot = AdminManagementService.build_admin_snapshot(admin)

    assert "password_hash" not in snapshot
    assert snapshot["email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_create_admin_user_endpoint_returns_created_admin(monkeypatch):
    from admin_service.api.v1.endpoints.admin_users import create_admin_user
    from admin_service.management_schemas import CreateAdminRequest
    from admin_service.models import AdminUser

    now = datetime.now()
    current_admin = AdminUser(
        uid=1,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )
    created_admin = SimpleNamespace(
        uid=1002,
        email="admin@example.com",
        name="Admin",
        role="admin",
        status=1,
        created_at=now,
        updated_at=now,
    )

    async def fake_create_admin(*args, **kwargs):
        return created_admin

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.admin_users.AdminManagementService.create_admin",
        fake_create_admin,
    )

    response = await create_admin_user(
        payload=CreateAdminRequest(
            email="admin@example.com",
            name="Admin",
            password="StrongPassword123!",
        ),
        request=SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest"},
        ),
        current_admin=current_admin,
        db=object(),
    )

    assert response.data.uid == "1002"
    assert response.data.role == "admin"


@pytest.mark.asyncio
async def test_list_admin_users_endpoint_returns_paginated_items(monkeypatch):
    from admin_service.api.v1.endpoints.admin_users import list_admin_users
    from admin_service.models import AdminUser

    now = datetime.now()
    current_admin = AdminUser(
        uid=1,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )
    listed_admin = SimpleNamespace(
        uid=1002,
        email="admin@example.com",
        name="Admin",
        role="admin",
        status=1,
        last_login_at=None,
        created_at=now,
        updated_at=now,
    )

    async def fake_list_admins(*args, **kwargs):
        return [listed_admin], 1

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.admin_users.AdminManagementService.list_admins",
        fake_list_admins,
    )

    response = await list_admin_users(
        page=1,
        page_size=20,
        current_admin=current_admin,
        db=object(),
    )

    assert response.data.total == 1
    assert response.data.items[0].uid == "1002"


@pytest.mark.asyncio
async def test_list_admin_audit_logs_endpoint_returns_paginated_items(monkeypatch):
    from admin_service.api.v1.endpoints.admin_audit_logs import list_admin_audit_logs
    from admin_service.models import AdminUser

    captured = {}
    now = datetime.now()
    current_admin = AdminUser(
        uid=1,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )
    actor_admin = SimpleNamespace(
        uid=1,
        email="super@example.com",
        name="Super",
        role="super_admin",
    )
    target_admin = SimpleNamespace(
        uid=1002,
        email="admin@example.com",
        name="Admin",
        role="admin",
    )
    audit_log = SimpleNamespace(
        id=11,
        actor_admin=actor_admin,
        target_admin=target_admin,
        action="create_admin",
        resource_type="admin_user",
        resource_id="1002",
        status="success",
        reason=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
        before_data=None,
        after_data={"uid": 1002},
        created_at=now,
    )

    async def fake_list_logs(*args, **kwargs):
        captured.update(kwargs)
        return [audit_log], 1

    monkeypatch.setattr(
        "admin_service.api.v1.endpoints.admin_audit_logs.AdminAuditService.list_logs",
        fake_list_logs,
    )

    response = await list_admin_audit_logs(
        page=1,
        page_size=20,
        category="governance",
        action=None,
        actor_uid=None,
        target_uid=None,
        current_admin=current_admin,
        db=object(),
    )

    assert response.data.total == 1
    assert response.data.items[0].action == "create_admin"
    assert response.data.items[0].actor_admin.email == "super@example.com"
    assert response.data.items[0].target_admin.name == "Admin"
    assert captured["category"] == "governance"


@pytest.mark.asyncio
async def test_admin_audit_service_list_logs_filters_governance_category():
    from admin_service.services.audit_service import AdminAuditService

    fake_log = SimpleNamespace(action="create_admin")
    db = _CaptureDB(
        _FakeResult(scalar_value=1),
        _FakeResult(scalars_value=[fake_log]),
    )

    logs, total = await AdminAuditService.list_logs(db, category="governance")

    assert logs == [fake_log]
    assert total == 1
    count_query_sql = str(
        db.statements[0].compile(compile_kwargs={"literal_binds": True, "render_postcompile": True})
    )
    data_query_sql = str(
        db.statements[1].compile(compile_kwargs={"literal_binds": True, "render_postcompile": True})
    )
    assert "create_admin" in count_query_sql
    assert "reset_admin_password" in data_query_sql
    assert "admin_login_success" not in data_query_sql


@pytest.mark.asyncio
async def test_admin_audit_service_list_logs_filters_auth_category():
    from admin_service.services.audit_service import AdminAuditService

    fake_log = SimpleNamespace(action="admin_login_success")
    db = _CaptureDB(
        _FakeResult(scalar_value=1),
        _FakeResult(scalars_value=[fake_log]),
    )

    logs, total = await AdminAuditService.list_logs(db, category="auth")

    assert logs == [fake_log]
    assert total == 1
    data_query_sql = str(
        db.statements[1].compile(compile_kwargs={"literal_binds": True, "render_postcompile": True})
    )
    assert "admin_login_success" in data_query_sql
    assert "admin_login_locked" in data_query_sql
    assert "create_admin" not in data_query_sql


@pytest.mark.asyncio
async def test_admin_audit_service_list_logs_keeps_all_category_unfiltered():
    from admin_service.services.audit_service import AdminAuditService

    fake_log = SimpleNamespace(action="create_admin")
    db = _CaptureDB(
        _FakeResult(scalar_value=1),
        _FakeResult(scalars_value=[fake_log]),
    )

    logs, total = await AdminAuditService.list_logs(db, category="all")

    assert logs == [fake_log]
    assert total == 1
    data_query_sql = str(
        db.statements[1].compile(compile_kwargs={"literal_binds": True, "render_postcompile": True})
    )
    assert "admin_audit_logs.action IN" not in data_query_sql


@pytest.mark.asyncio
async def test_bootstrap_cli_runs_bootstrap_flow(monkeypatch):
    from admin_service.bootstrap_superadmin import async_main

    calls = []
    fake_settings = SimpleNamespace(
        LOG_LEVEL="INFO",
        BOOTSTRAP_SUPERADMIN_ENABLED=True,
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True,
    )

    async def fake_setup_runtime(*, skip_init_db):
        calls.append(("setup", skip_init_db))

    async def fake_ensure_super_admin():
        calls.append("ensure")
        return True

    async def fake_close_db():
        calls.append("close")

    monkeypatch.setattr("admin_service.bootstrap_superadmin.settings", fake_settings)
    monkeypatch.setattr("admin_service.bootstrap_superadmin._setup_runtime", fake_setup_runtime)
    monkeypatch.setattr("admin_service.bootstrap_superadmin.close_db", fake_close_db)
    monkeypatch.setattr(
        "admin_service.bootstrap_superadmin.AdminBootstrapService.ensure_super_admin",
        fake_ensure_super_admin,
    )

    exit_code = await async_main([])

    assert exit_code == 0
    assert calls == [("setup", False), "ensure", "close"]


@pytest.mark.asyncio
async def test_bootstrap_cli_check_only_returns_nonzero_when_missing(monkeypatch):
    from admin_service.bootstrap_superadmin import async_main

    calls = []
    fake_settings = SimpleNamespace(
        LOG_LEVEL="INFO",
        BOOTSTRAP_SUPERADMIN_ENABLED=False,
        BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True,
    )

    async def fake_setup_runtime(*, skip_init_db):
        calls.append(("setup", skip_init_db))

    async def fake_run_check_only():
        calls.append("check")
        return 1

    async def fake_close_db():
        calls.append("close")

    monkeypatch.setattr("admin_service.bootstrap_superadmin.settings", fake_settings)
    monkeypatch.setattr("admin_service.bootstrap_superadmin._setup_runtime", fake_setup_runtime)
    monkeypatch.setattr("admin_service.bootstrap_superadmin._run_check_only", fake_run_check_only)
    monkeypatch.setattr("admin_service.bootstrap_superadmin.close_db", fake_close_db)

    exit_code = await async_main(["--check-only", "--skip-init-db"])

    assert exit_code == 1
    assert calls == [("setup", True), "check", "close"]


class _FakeScalarResult:
    def __init__(self, admin):
        self._admin = admin

    def scalar_one_or_none(self):
        return self._admin


class _FakeAuthDB:
    def __init__(self, admin):
        self.admin = admin
        self.commit_count = 0

    async def execute(self, _query):
        return _FakeScalarResult(self.admin)

    async def commit(self):
        self.commit_count += 1


class _FakeResult:
    def __init__(self, *, scalar_value=None, scalar_one_or_none_value=None, scalars_value=None):
        self._scalar_value = scalar_value
        self._scalar_one_or_none_value = scalar_one_or_none_value
        self._scalars_value = scalars_value or []

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalar_one_or_none_value

    def scalars(self):
        return self

    def all(self):
        return self._scalars_value


class _CaptureDB:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_auth_login_success_records_success_audit(monkeypatch):
    from admin_service.models import AdminUser
    from admin_service.services.auth_service import AdminAuthService

    admin = AdminUser(
        uid=101,
        email="admin@example.com",
        password_hash="hash",
        name="Admin",
        role="admin",
        status=1,
    )
    admin.id = 7
    db = _FakeAuthDB(admin)
    audit_actions = []

    async def fake_record(*args, **kwargs):
        audit_actions.append(kwargs["action"])

    monkeypatch.setattr("admin_service.services.auth_service.verify_password", lambda *_args: True)
    monkeypatch.setattr("admin_service.services.auth_service.create_access_token", lambda **_kwargs: "token")
    monkeypatch.setattr("admin_service.services.auth_service.AdminAuditService.record", fake_record)

    result_admin, token = await AdminAuthService.login(
        db,
        email="admin@example.com",
        password="StrongPassword123!",
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    assert result_admin is admin
    assert token == "token"
    assert audit_actions == ["admin_login_success"]
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_auth_login_failure_can_lock_account_and_emit_audit(monkeypatch):
    from admin_service.models import AdminUser
    from admin_service.services.auth_service import AdminAuthService
    from common.core.exceptions import InvalidCredentialsException

    admin = AdminUser(
        uid=102,
        email="admin@example.com",
        password_hash="hash",
        name="Admin",
        role="admin",
        status=1,
    )
    admin.id = 8
    admin.login_fail_count = 4
    db = _FakeAuthDB(admin)
    audit_actions = []

    async def fake_record(*args, **kwargs):
        audit_actions.append(kwargs["action"])

    monkeypatch.setattr("admin_service.services.auth_service.verify_password", lambda *_args: False)
    monkeypatch.setattr("admin_service.services.auth_service.AdminAuditService.record", fake_record)

    with pytest.raises(InvalidCredentialsException):
        await AdminAuthService.login(
            db,
            email="admin@example.com",
            password="wrong-password",
            user_agent="pytest",
            ip_address="127.0.0.1",
        )

    assert audit_actions == ["admin_login_failed", "admin_login_locked"]
    assert admin.login_fail_count == 5
    assert admin.login_locked_until is not None
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_auth_login_after_lock_expired_records_unlock_audit(monkeypatch):
    from admin_service.models import AdminUser
    from admin_service.services.auth_service import AdminAuthService

    admin = AdminUser(
        uid=103,
        email="admin@example.com",
        password_hash="hash",
        name="Admin",
        role="admin",
        status=1,
    )
    admin.id = 9
    admin.login_fail_count = 5
    admin.login_locked_until = datetime.now() - timedelta(minutes=5)
    db = _FakeAuthDB(admin)
    audit_actions = []

    async def fake_record(*args, **kwargs):
        audit_actions.append(kwargs["action"])

    monkeypatch.setattr("admin_service.services.auth_service.verify_password", lambda *_args: True)
    monkeypatch.setattr("admin_service.services.auth_service.create_access_token", lambda **_kwargs: "token")
    monkeypatch.setattr("admin_service.services.auth_service.AdminAuditService.record", fake_record)

    _, token = await AdminAuthService.login(
        db,
        email="admin@example.com",
        password="StrongPassword123!",
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    assert token == "token"
    assert audit_actions == ["admin_login_success", "admin_login_unlocked"]
    assert admin.login_fail_count == 0
    assert admin.login_locked_until is None


