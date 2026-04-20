"""Basic user-service smoke tests."""

from datetime import datetime
import importlib
import inspect
import os
import sys
from types import SimpleNamespace

import pytest

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


class TestUserConfig:
    def test_config_import(self):
        from user_service.config import settings

        assert settings is not None
        assert settings.PORT == 8000
        assert settings.JWT_ALGORITHM == "HS256"

    def test_config_values(self):
        from user_service.config import settings

        assert settings.PORT == 8000
        # Post-consolidation: admin/user/testing all live inside backend-app on :8001.
        assert settings.ADMIN_SERVICE_URL == "http://localhost:8001"


class TestUserModels:
    def test_user_model_import(self):
        from user_service.models import User

        assert User.__tablename__ == "users"

    def test_user_model_fields(self):
        from user_service.models import User

        assert hasattr(User, "uid")
        assert hasattr(User, "email")
        assert hasattr(User, "password_hash")
        assert hasattr(User, "status")

    def test_user_model_properties(self):
        from user_service.models import User

        user = User(
            uid=12345,
            email="test@example.com",
            password_hash="hash",
            status=1,
        )

        assert user.is_active is True
        assert user.is_email_verified is False

    def test_user_session_model(self):
        from user_service.models import UserSession

        assert UserSession.__tablename__ == "user_sessions"

    def test_extended_user_models_use_local_foreign_keys(self):
        from user_service.models import ApiCallLog, BalanceTransaction, TopupOrder, UsageStat

        assert BalanceTransaction.__table__.c.user_id.foreign_keys
        assert TopupOrder.__table__.c.user_id.foreign_keys
        assert ApiCallLog.__table__.c.user_id.foreign_keys
        assert ApiCallLog.__table__.c.api_key_id.foreign_keys
        assert UsageStat.__table__.c.user_id.foreign_keys
        assert UsageStat.__table__.c.api_key_id.foreign_keys


class TestUserUtils:
    def test_password_strength_check(self):
        from user_service.utils.password import check_password_strength

        ok, _msg = check_password_strength("weak")
        assert ok is False

        ok, _msg = check_password_strength("StrongPassword123!")
        assert ok is True


class TestUserSchemas:
    def test_login_request(self):
        from user_service.schemas import LoginRequest

        req = LoginRequest(email="test@example.com", password="password123")
        assert req.email == "test@example.com"
        assert req.password == "password123"

    def test_register_request(self):
        from user_service.schemas import RegisterRequest

        req = RegisterRequest(
            invitation_code="INVITE123",
            email="test@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
            verification_code="123456",
        )
        assert req.email == "test@example.com"
        assert req.invitation_code == "INVITE123"

    def test_register_request_normalizes_email(self):
        from user_service.schemas import RegisterRequest

        req = RegisterRequest(
            invitation_code="INVITE123",
            email="  Test@Example.com  ",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
            verification_code="123456",
        )

        assert req.email == "test@example.com"

    def test_login_request_normalizes_email(self):
        from user_service.schemas import LoginRequest

        req = LoginRequest(email="  Test@Example.com  ", password="password123")

        assert req.email == "test@example.com"

    def test_register_request_uses_lang_for_password_errors(self):
        from pydantic import ValidationError
        from user_service.schemas import RegisterRequest

        with pytest.raises(ValidationError, match="Password must contain at least one uppercase letter"):
            RegisterRequest(
                invitation_code="INVITE123",
                email="test@example.com",
                password="weakpass1!",
                confirm_password="weakpass1!",
                verification_code="123456",
                lang="en",
            )

    def test_user_info_response(self):
        from user_service.schemas import UserInfoResponseData

        data = UserInfoResponseData(
            uid=12345,
            email="test@example.com",
            status=1,
            created_at=datetime.now(),
        )
        assert data.uid == 12345
        assert data.status == 1

    def test_login_response_contains_full_user_info(self):
        from user_service.schemas import LoginResponseData, UserData

        now = datetime.now()
        data = LoginResponseData(
            user=UserData(
                uid=12345,
                email="test@example.com",
                status=1,
                email_verified_at=now,
                last_login_at=now,
                created_at=now,
            ),
            access_token="token",
            expires_in=3600,
        )

        assert data.user.uid == 12345
        assert data.user.status == 1
        assert data.user.created_at == now

    def test_send_email_code_request_accepts_verify_purpose(self):
        from user_service.schemas import SendEmailCodeRequest

        request = SendEmailCodeRequest(email="user@example.com", purpose="verify")

        assert request.purpose == "verify"

    def test_send_email_code_request_rejects_unknown_purpose(self):
        from pydantic import ValidationError
        from user_service.schemas import SendEmailCodeRequest

        with pytest.raises(ValidationError):
            SendEmailCodeRequest(email="user@example.com", purpose="unknown")

    def test_change_password_request_uses_lang_for_password_errors(self):
        from pydantic import ValidationError
        from user_service.schemas import ChangePasswordRequest

        with pytest.raises(ValidationError, match="Password must contain at least one uppercase letter"):
            ChangePasswordRequest(
                old_password="OldPassword123!",
                new_password="weakpass1!",
                lang="en",
            )


class TestUserServices:
    def test_auth_service_import(self):
        from user_service.services import AuthService

        assert AuthService is not None

    def test_email_service_import(self):
        from user_service.services import email_service

        assert email_service is not None

    def test_email_service_uses_repository_boundary(self):
        email_service_module = importlib.import_module("user_service.services.email_service")

        source = inspect.getsource(email_service_module.EmailService)

        assert "db.execute(" not in source
        assert "select(" not in source
        assert "db.delete(" not in source
        assert "db.add(" not in source

    @pytest.mark.asyncio
    async def test_register_persists_invitation_release_outbox_when_release_fails(
        self, monkeypatch
    ):
        from user_service.models import InvitationReleaseOutbox
        from user_service.schemas import RegisterRequest
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def scalar_one_or_none(self):
                return None

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("user@example.com", "123456", "register")
            return SimpleNamespace(used_at=None, error_count=0)

        async def fake_consume_invitation_code(code, used_by_uid):
            assert (code, used_by_uid) == ("invite-code", 84)

        async def fail_release_invitation_code(code, used_by_uid):
            assert (code, used_by_uid) == ("invite-code", 84)
            raise RuntimeError("release failed")

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.AuthService._admin_gateway.consume_invitation_code",
            fake_consume_invitation_code,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.AuthService._admin_gateway.release_invitation_code",
            fail_release_invitation_code,
        )
        monkeypatch.setattr(
            "user_service.utils.password.check_password_strength",
            lambda password, lang="zh": (True, ""),
        )
        monkeypatch.setattr("user_service.services.auth_service.generate_snowflake_id", lambda: 84)

        class FakeSession:
            def __init__(self):
                self.added = []
                self.rollback_called = False
                self.commit_calls = 0

            async def execute(self, _statement):
                return ScalarResult()

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                self.commit_calls += 1
                if self.commit_calls == 1:
                    raise RuntimeError("commit failed")

            async def rollback(self):
                self.rollback_called = True

            async def refresh(self, _obj):
                raise AssertionError("refresh should not be called")

        db = FakeSession()
        request = RegisterRequest(
            invitation_code="invite-code",
            email="user@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
            verification_code="123456",
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            await AuthService.register(db, request)

        outbox_entries = [obj for obj in db.added if isinstance(obj, InvitationReleaseOutbox)]
        assert len(outbox_entries) == 1
        assert outbox_entries[0].code == "invite-code"
        assert outbox_entries[0].used_by_uid == 84
        assert outbox_entries[0].last_error == "release failed"
        assert db.rollback_called is True
        assert db.commit_calls == 2

    @pytest.mark.asyncio
    async def test_register_persists_invitation_release_outbox_when_release_returns_false(
        self, monkeypatch
    ):
        from user_service.models import InvitationReleaseOutbox
        from user_service.schemas import RegisterRequest
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def scalar_one_or_none(self):
                return None

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("user@example.com", "123456", "register")
            return SimpleNamespace(used_at=None, error_count=0)

        async def fake_consume_invitation_code(code, used_by_uid):
            assert (code, used_by_uid) == ("invite-code", 84)

        async def false_release_invitation_code(code, used_by_uid):
            assert (code, used_by_uid) == ("invite-code", 84)
            return False

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.AuthService._admin_gateway.consume_invitation_code",
            fake_consume_invitation_code,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.AuthService._admin_gateway.release_invitation_code",
            false_release_invitation_code,
        )
        monkeypatch.setattr(
            "user_service.utils.password.check_password_strength",
            lambda password, lang="zh": (True, ""),
        )
        monkeypatch.setattr("user_service.services.auth_service.generate_snowflake_id", lambda: 84)

        class FakeSession:
            def __init__(self):
                self.added = []
                self.rollback_called = False
                self.commit_calls = 0

            async def execute(self, _statement):
                return ScalarResult()

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                self.commit_calls += 1
                if self.commit_calls == 1:
                    raise RuntimeError("commit failed")

            async def rollback(self):
                self.rollback_called = True

            async def refresh(self, _obj):
                raise AssertionError("refresh should not be called")

        db = FakeSession()
        request = RegisterRequest(
            invitation_code="invite-code",
            email="user@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
            verification_code="123456",
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            await AuthService.register(db, request)

        outbox_entries = [obj for obj in db.added if isinstance(obj, InvitationReleaseOutbox)]
        assert len(outbox_entries) == 1
        assert outbox_entries[0].code == "invite-code"
        assert outbox_entries[0].used_by_uid == 84
        assert "returned false" in outbox_entries[0].last_error
        assert db.rollback_called is True
        assert db.commit_calls == 2

    @pytest.mark.asyncio
    async def test_verify_email_rejects_disabled_user(self, monkeypatch):
        from common.core.exceptions import UserDisabledException
        from user_service.models import User
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

        disabled_user = User(
            uid=12345,
            email="disabled@example.com",
            password_hash="hash",
            status=0,
        )

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("disabled@example.com", "123456", "verify")
            return SimpleNamespace(used_at=None, error_count=0)

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0

            async def execute(self, _statement):
                return ScalarResult(disabled_user)

            async def commit(self):
                self.commit_calls += 1

            async def refresh(self, _obj):
                raise AssertionError("refresh should not be called for disabled users")

        db = FakeSession()

        with pytest.raises(UserDisabledException):
            await AuthService.verify_email(db, "disabled@example.com", "123456")

        assert disabled_user.status == 0
        assert db.commit_calls == 0

    @pytest.mark.asyncio
    async def test_send_verification_code_does_not_persist_on_email_send_failure(
        self, monkeypatch
    ):
        from user_service.services.email_service import email_service

        class CountResult:
            def scalar(self):
                return 0

        class LatestResult:
            def scalar_one_or_none(self):
                return None

        class OldCodesResult:
            def scalars(self):
                return SimpleNamespace(all=lambda: [SimpleNamespace(code="old")])

        async def fake_execute(_statement):
            fake_execute.calls += 1
            if fake_execute.calls == 1:
                return CountResult()
            if fake_execute.calls == 2:
                return LatestResult()
            return OldCodesResult()

        fake_execute.calls = 0

        monkeypatch.setattr(
            email_service,
            "_send_email",
            lambda email, code, purpose: (False, "Email send failed"),
        )
        monkeypatch.setattr(
            email_service,
            "generate_code",
            lambda: "123456",
        )

        class FakeSession:
            def __init__(self):
                self.deleted = []
                self.added = []
                self.flush_calls = 0
                self.commit_calls = 0

            async def execute(self, statement):
                return await fake_execute(statement)

            async def delete(self, obj):
                self.deleted.append(obj)

            def add(self, obj):
                self.added.append(obj)

            async def flush(self):
                self.flush_calls += 1

            async def commit(self):
                self.commit_calls += 1

            async def rollback(self):
                raise AssertionError("rollback should not be needed")

        db = FakeSession()

        success, message = await email_service.send_verification_code(
            db, "user@example.com", "register"
        )

        assert success is False
        assert message == "Email send failed"
        assert db.deleted == []
        assert db.added == []
        assert db.flush_calls == 0
        assert db.commit_calls == 0

    @pytest.mark.asyncio
    async def test_change_password_commits_once_after_revoking_sessions(self, monkeypatch):
        from user_service.models import User, UserSession
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, values):
                self.values = values

            def scalars(self):
                return SimpleNamespace(all=lambda: self.values)

        monkeypatch.setattr(
            "user_service.services.auth_service.verify_password",
            lambda plain, hashed: plain == "old-password" and hashed == "old-hash",
        )
        monkeypatch.setattr(
            "user_service.utils.password.check_password_strength",
            lambda password, lang="zh": (True, ""),
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.hash_password",
            lambda password: f"hashed::{password}",
        )

        user = User(
            uid=1,
            email="user@example.com",
            password_hash="old-hash",
            status=1,
        )
        sessions = [
            UserSession(session_id=10, user_id=99, token_jti="a", refresh_token_hash="h", expires_at=datetime.now()),
            UserSession(session_id=11, user_id=99, token_jti="b", refresh_token_hash="h", expires_at=datetime.now()),
        ]

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0
                self.revoked_at_commit = False

            async def execute(self, _statement):
                return ScalarResult(sessions)

            async def commit(self):
                self.commit_calls += 1
                self.revoked_at_commit = all(session.revoked_at is not None for session in sessions)

        db = FakeSession()

        await AuthService.change_password(
            db, user, "old-password", "StrongPassword123!", "zh"
        )

        assert user.password_hash == "hashed::StrongPassword123!"
        assert db.commit_calls == 1
        assert db.revoked_at_commit is True
        assert all(session.revoked_at is not None for session in sessions)

    def test_usage_stat_service_uses_repository_boundary(self):
        import user_service.services.usage_stat_service as usage_stat_service_module

        source = inspect.getsource(usage_stat_service_module.UsageStatService)

        assert "db.execute(" not in source
        assert "select(" not in source
        assert "db.add(" not in source

    @pytest.mark.asyncio
    async def test_login_commits_once_for_session_rotation(self, monkeypatch):
        from user_service.models import User, UserSession
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

            def scalars(self):
                return SimpleNamespace(all=lambda: self.value)

        user = User(
            id=77,
            uid=12345,
            email="user@example.com",
            password_hash="stored-hash",
            status=1,
        )
        existing_sessions = [
            UserSession(session_id=1, user_id=77, token_jti="j1", refresh_token_hash="h", expires_at=datetime.now())
        ]

        monkeypatch.setattr(
            "user_service.services.auth_service.verify_password",
            lambda plain, hashed: plain == "correct-password" and hashed == "stored-hash",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.create_access_token",
            lambda **kwargs: "access-token",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.create_refresh_token",
            lambda **kwargs: "refresh-token",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.get_token_jti",
            lambda token: "jti-value",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.hash_password",
            lambda token: f"hash::{token}",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.generate_snowflake_id",
            lambda: 999,
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0
                self.added = []
                self.execute_calls = 0

            async def execute(self, _statement):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    return ScalarResult(user)
                return ScalarResult(existing_sessions)

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                self.commit_calls += 1

        db = FakeSession()

        logged_in_user, access_token, refresh_token = await AuthService.login(
            db, "user@example.com", "correct-password", "UA", "127.0.0.1"
        )

        assert logged_in_user is user
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert db.commit_calls == 1
        assert all(session.revoked_at is not None for session in existing_sessions)
        assert len(db.added) == 1
        assert isinstance(db.added[0], UserSession)

    @pytest.mark.asyncio
    async def test_login_with_code_resets_password_failure_lock_state(self, monkeypatch):
        from datetime import timedelta

        from common.utils.timezone import now
        from user_service.models import User, UserSession
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

            def scalars(self):
                return SimpleNamespace(all=lambda: [])

        code_record = SimpleNamespace(used_at=None, error_count=0)
        user = User(
            id=77,
            uid=12345,
            email="user@example.com",
            password_hash="stored-hash",
            status=1,
            login_fail_count=4,
            login_locked_until=now() + timedelta(minutes=20),
        )

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("user@example.com", "123456", "login")
            return code_record

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.create_access_token",
            lambda **kwargs: "access-token",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.create_refresh_token",
            lambda **kwargs: "refresh-token",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.get_token_jti",
            lambda token: "jti-value",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.hash_password",
            lambda token: f"hash::{token}",
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.generate_snowflake_id",
            lambda: 999,
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0
                self.added = []
                self.execute_calls = 0

            async def execute(self, _statement):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    return ScalarResult(user)
                return ScalarResult([])

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                self.commit_calls += 1

        db = FakeSession()

        logged_in_user, access_token, refresh_token = await AuthService.login_with_code(
            db, "USER@example.com", "123456", "UA", "127.0.0.1"
        )

        assert logged_in_user is user
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert user.login_fail_count == 0
        assert user.login_locked_until is None
        assert code_record.used_at is not None
        assert db.commit_calls == 1
        assert len(db.added) == 1
        assert isinstance(db.added[0], UserSession)

    @pytest.mark.asyncio
    async def test_reset_password_does_not_consume_code_when_user_missing(self, monkeypatch):
        import importlib
        from datetime import timedelta

        from common.core.exceptions import UserNotFoundException
        from common.utils.timezone import now
        from user_service.services.auth_service import AuthService

        email_service_module = importlib.import_module("user_service.services.email_service")

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

        record = SimpleNamespace(
            email="missing@example.com",
            purpose="reset_password",
            code_hash="stored-hash",
            expires_at=now() + timedelta(minutes=5),
            locked_until=None,
            used_at=None,
            error_count=0,
        )

        monkeypatch.setattr(
            email_service_module,
            "verify_password",
            lambda plain, hashed: plain == "123456" and hashed == "stored-hash",
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0
                self.execute_calls = 0

            async def execute(self, _statement):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    return ScalarResult(record)
                return ScalarResult(None)

            async def commit(self):
                self.commit_calls += 1

        db = FakeSession()

        with pytest.raises(UserNotFoundException):
            await AuthService.reset_password(
                db,
                "missing@example.com",
                "123456",
                "StrongPassword123!",
                "zh",
            )

        assert record.used_at is None
        assert db.commit_calls == 0

    @pytest.mark.asyncio
    async def test_reset_password_rejects_disabled_user_without_consuming_code(self, monkeypatch):
        from common.core.exceptions import UserDisabledException
        from user_service.models import User
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

        code_record = SimpleNamespace(used_at=None, error_count=0)
        disabled_user = User(
            id=77,
            uid=12345,
            email="disabled@example.com",
            password_hash="stored-hash",
            status=0,
        )

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("disabled@example.com", "123456", "reset_password")
            return code_record

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.mark_code_used",
            lambda _record: (_ for _ in ()).throw(
                AssertionError("disabled users must not consume reset codes")
            ),
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0

            async def execute(self, _statement):
                return ScalarResult(disabled_user)

            async def commit(self):
                self.commit_calls += 1

        db = FakeSession()

        with pytest.raises(UserDisabledException):
            await AuthService.reset_password(
                db,
                "disabled@example.com",
                "123456",
                "StrongPassword123!",
                "zh",
            )

        assert code_record.used_at is None
        assert db.commit_calls == 0

    @pytest.mark.asyncio
    async def test_reset_password_commits_after_revoking_sessions(self, monkeypatch):
        from user_service.models import User, UserSession
        from user_service.services.auth_service import AuthService

        class ScalarResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

            def scalars(self):
                return SimpleNamespace(all=lambda: self.value)

        code_record = SimpleNamespace(used_at=None, error_count=0)
        user = User(
            id=77,
            uid=12345,
            email="user@example.com",
            password_hash="stored-hash",
            status=1,
        )
        sessions = [
            UserSession(session_id=10, user_id=77, token_jti="a", refresh_token_hash="h", expires_at=datetime.now()),
            UserSession(session_id=11, user_id=77, token_jti="b", refresh_token_hash="h", expires_at=datetime.now()),
        ]

        async def fake_get_valid_code_or_raise(_db, email, code, purpose):
            assert (email, code, purpose) == ("user@example.com", "123456", "reset_password")
            return code_record

        monkeypatch.setattr(
            "user_service.services.auth_service.email_service.get_valid_code_or_raise",
            fake_get_valid_code_or_raise,
        )
        monkeypatch.setattr(
            "user_service.utils.password.check_password_strength",
            lambda password, lang="zh": (True, ""),
        )
        monkeypatch.setattr(
            "user_service.services.auth_service.hash_password",
            lambda password: f"hashed::{password}",
        )

        class FakeSession:
            def __init__(self):
                self.commit_calls = 0
                self.revoked_at_commit = False
                self.execute_calls = 0

            async def execute(self, _statement):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    return ScalarResult(user)
                return ScalarResult(sessions)

            async def commit(self):
                self.commit_calls += 1
                self.revoked_at_commit = all(session.revoked_at is not None for session in sessions)

        db = FakeSession()

        await AuthService.reset_password(
            db,
            "user@example.com",
            "123456",
            "StrongPassword123!",
            "zh",
        )

        assert user.password_hash == "hashed::StrongPassword123!"
        assert code_record.used_at is not None
        assert db.commit_calls == 1
        assert db.revoked_at_commit is True
        assert all(session.revoked_at is not None for session in sessions)


class TestUserAPI:
    def test_dependencies_import(self):
        from user_service.dependencies import get_current_user, get_db_session

        assert get_current_user is not None
        assert get_db_session is not None

    @pytest.mark.asyncio
    async def test_get_current_user_returns_pending_user_without_policy(self, monkeypatch):
        from fastapi.security import HTTPAuthorizationCredentials

        from user_service.dependencies import get_current_user
        from user_service.models import User

        pending_user = User(
            uid=12345,
            email="pending@example.com",
            password_hash="hash",
            status=2,
        )

        async def fake_get_current_user(_db, uid):
            assert uid == 12345
            return pending_user

        monkeypatch.setattr(
            "user_service.dependencies.decode_token",
            lambda **kwargs: {"type": "access", "uid": 12345},
        )
        monkeypatch.setattr(
            "user_service.dependencies.AuthService.get_current_user",
            fake_get_current_user,
        )

        current_user = await get_current_user(
            request=object(),
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="access-token",
            ),
            access_token=None,
            db=object(),
        )

        assert current_user is pending_user

    @pytest.mark.asyncio
    async def test_verify_email_endpoint_delegates_to_auth_service(self, monkeypatch):
        from user_service.api.v1.endpoints.auth import verify_email
        from user_service.schemas import VerifyEmailRequest

        captured = {}

        async def fake_verify_email(db, email, code):
            captured["call"] = (db, email, code)
            return SimpleNamespace(status=1, email_verified_at=datetime.now())

        async def fail_if_called(*_args, **_kwargs):
            raise AssertionError("endpoint should delegate to AuthService.verify_email")

        monkeypatch.setattr(
            "user_service.api.v1.endpoints.auth.AuthService.verify_email",
            fake_verify_email,
        )
        monkeypatch.setattr(
            "user_service.api.v1.endpoints.auth.email_service.verify_code_or_raise",
            fail_if_called,
        )

        db = object()
        response = await verify_email(
            VerifyEmailRequest(email="user@example.com", code="123456"),
            db=db,
        )

        assert captured["call"] == (db, "user@example.com", "123456")
        assert response.code == 200
        assert response.message == "邮箱验证成功"

    @pytest.mark.asyncio
    async def test_send_email_code_raises_when_service_reports_failure(self, monkeypatch):
        from common.core.exceptions import ServiceUnavailableException
        from user_service.api.v1.endpoints.auth import send_email_code
        from user_service.schemas import SendEmailCodeRequest

        async def fake_send_verification_code(_db, email, purpose):
            assert (email, purpose) == ("user@example.com", "register")
            return False, "Email send failed"

        monkeypatch.setattr(
            "user_service.api.v1.endpoints.auth.email_service.send_verification_code",
            fake_send_verification_code,
        )

        with pytest.raises(ServiceUnavailableException, match="Email send failed"):
            await send_email_code(
                SendEmailCodeRequest(email="user@example.com", purpose="register"),
                db=object(),
            )

    @pytest.mark.asyncio
    async def test_register_endpoint_passes_request_metadata_to_login(self, monkeypatch):
        from fastapi import Response

        from user_service.api.v1.endpoints.auth import register
        from user_service.schemas import RegisterRequest

        created_user = SimpleNamespace(
            email="user@example.com",
        )
        logged_in_user = SimpleNamespace(
            uid=12345,
            email="user@example.com",
            created_at=datetime.now(),
        )
        captured = {}

        async def fake_register(_db, request):
            assert request.email == "user@example.com"
            return created_user

        async def fake_login(_db, email, password, user_agent, ip_address):
            captured["login"] = (email, password, user_agent, ip_address)
            return logged_in_user, "access-token", "refresh-token"

        monkeypatch.setattr(
            "user_service.api.v1.endpoints.auth.AuthService.register",
            fake_register,
        )
        monkeypatch.setattr(
            "user_service.api.v1.endpoints.auth.AuthService.login",
            fake_login,
        )

        response = Response()
        result = await register(
            RegisterRequest(
                invitation_code="INVITE123",
                email="user@example.com",
                password="StrongPassword123!",
                confirm_password="StrongPassword123!",
                verification_code="123456",
            ),
            response=response,
            db=object(),
            request_obj=SimpleNamespace(
                headers={"user-agent": "TestAgent/1.0"},
                client=SimpleNamespace(host="127.0.0.1"),
            ),
        )

        assert captured["login"] == (
            "user@example.com",
            "StrongPassword123!",
            "TestAgent/1.0",
            "127.0.0.1",
        )
        assert result.code == 201


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
