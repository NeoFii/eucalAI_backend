"""Basic user-service smoke tests."""

from datetime import datetime
import os
import sys

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
        # Post-consolidation: admin/testing live inside backend-app on :8001.
        # router-service keeps its dedicated port for scaling.
        assert settings.ADMIN_SERVICE_URL == "http://localhost:8001"
        assert settings.ROUTER_SERVICE_URL == "http://localhost:8003"


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


class TestUserServices:
    def test_auth_service_import(self):
        from user_service.services import AuthService

        assert AuthService is not None

    def test_email_service_import(self):
        from user_service.services import email_service

        assert email_service is not None


class TestUserAPI:
    def test_dependencies_import(self):
        from user_service.dependencies import get_current_user, get_db_session, get_optional_user

        assert get_current_user is not None
        assert get_db_session is not None
        assert get_optional_user is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
