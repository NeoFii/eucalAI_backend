"""Admin-service smoke tests."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest

os.environ["INTERNAL_SECRET"] = "test_secret"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)


class TestAdminConfig:
    def test_config_import(self):
        from admin_service.config import settings

        assert settings is not None
        assert settings.PORT == 8001

    def test_config_values(self):
        from admin_service.config import settings

        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.INTERNAL_SECRET


class TestAdminModels:
    def test_admin_user_model(self):
        from admin_service.models import AdminUser

        assert AdminUser.__tablename__ == "admin_users"
        assert hasattr(AdminUser, "uid")
        assert hasattr(AdminUser, "email")
        assert hasattr(AdminUser, "password_hash")
        assert hasattr(AdminUser, "name")
        assert hasattr(AdminUser, "role")

    def test_admin_user_properties(self):
        from admin_service.models import AdminUser

        admin = AdminUser(
            uid=12345,
            email="admin@example.com",
            password_hash="hash",
            name="Admin",
            role="super_admin",
            status=1,
        )

        assert admin.is_active is True
        assert admin.is_super_admin is True

    def test_invitation_code_model_and_properties(self):
        from admin_service.models import InvitationCode

        code = InvitationCode(
            code="TEST123",
            status=0,
            created_by=1,
            expires_at=datetime.now() + timedelta(days=7),
        )

        assert InvitationCode.__tablename__ == "invitation_codes"
        assert code.is_valid is True
        assert code.is_used is False
        assert code.is_disabled is False

    def test_invitation_code_rejects_removed_legacy_kwargs(self):
        from admin_service.models import InvitationCode

        with pytest.raises(TypeError):
            InvitationCode(code="TEST123", type="register")


class TestAdminUtils:
    def test_password_strength_check(self):
        from admin_service.utils.password import check_password_strength

        ok, _ = check_password_strength("weak")
        assert ok is False

        ok, _ = check_password_strength("StrongPassword123!")
        assert ok is True


class TestAdminSchemas:
    def test_admin_login_request(self):
        from admin_service.schemas import AdminLoginRequest

        req = AdminLoginRequest(email="admin@example.com", password="Password123!")
        assert req.email == "admin@example.com"

    def test_generate_invitation_code_request(self):
        from admin_service.schemas import GenerateInvitationCodeRequest

        req = GenerateInvitationCodeRequest(quantity=5, expires_days=7, max_uses=1)
        assert req.quantity == 5
        assert req.expires_days == 7


class TestAdminServices:
    def test_auth_service_import(self):
        from admin_service.services.auth_service import AdminAuthService

        assert AdminAuthService is not None

    def test_invitation_service_import(self):
        from admin_service.services.invitation_service import InvitationCodeService

        assert InvitationCodeService is not None

    def test_generate_code(self):
        from admin_service.services.invitation_service import InvitationCodeService

        code = InvitationCodeService.generate_code(length=16)
        assert len(code) == 16


class TestAdminDependencies:
    def test_dependencies_import(self):
        from admin_service.dependencies import get_current_admin, get_db_session

        assert get_current_admin is not None
        assert get_db_session is not None


class TestAdminAuthEndpoints:
    @pytest.mark.asyncio
    async def test_refresh_requires_refresh_cookie(self):
        from fastapi import Response

        from admin_service.api.v1.endpoints.auth import refresh_token
        from common.core.exceptions import AuthenticationException

        with pytest.raises(AuthenticationException):
            await refresh_token(response=Response(), refresh_token=None)


class TestNewsModel:
    def test_news_model_import(self):
        from content_service.models.news import News

        assert News is not None
        assert News.__tablename__ == "news"

    def test_news_model_fields(self):
        from content_service.models.news import News

        assert hasattr(News, "uid")
        assert hasattr(News, "language")
        assert hasattr(News, "title")
        assert hasattr(News, "slug")
        assert hasattr(News, "summary")
        assert hasattr(News, "cover_image")
        assert hasattr(News, "content")
        assert hasattr(News, "status")
        assert hasattr(News, "published_at")
        assert hasattr(News, "author_id")

    def test_news_model_properties(self):
        from content_service.models.news import News

        news = News(
            uid=123456789,
            language="zh",
            title="Test News",
            slug="test-news",
            summary="Summary",
            cover_image="https://example.com/image.jpg",
            content="# Content",
            status=1,
            published_at=datetime.now(),
            author_id=1,
        )

        assert news.is_published is True
        news.status = 0
        assert news.is_draft is True
        news.status = 2
        assert news.is_offline is True


class TestNewsSchemas:
    def test_create_news_request(self):
        from admin_service.schemas import CreateNewsRequest

        req = CreateNewsRequest(
            title="Test News",
            slug="test-news",
            language="zh",
            content="# Content",
            status=1,
        )

        assert req.title == "Test News"
        assert req.slug == "test-news"
        assert req.language == "zh"
        assert req.status == 1

    def test_update_news_request(self):
        from admin_service.schemas import UpdateNewsRequest

        req = UpdateNewsRequest(title="Updated Title", status=2)
        assert req.title == "Updated Title"
        assert req.status == 2

    def test_news_data(self):
        from admin_service.schemas import NewsData

        data = NewsData(
            uid="123456789",
            language="zh",
            title="Test News",
            slug="test-news",
            summary="Summary",
            cover_image="https://example.com/image.jpg",
            content="# Content",
            status=1,
            published_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert data.uid == "123456789"
        assert data.language == "zh"
        assert data.title == "Test News"


class TestNewsService:
    def test_news_service_import(self):
        from content_service.services.news_service import NewsService

        assert NewsService is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
