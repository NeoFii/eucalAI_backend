"""
Admin 模块单元测试
测试管理员服务的配置、模型、服务等
"""

import os
import sys
import pytest

# 设置环境变量
os.environ.setdefault("INTERNAL_SECRET", "test_secret")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")

# 添加 backend 到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


class TestAdminConfig:
    """测试管理员服务配置"""

    def test_config_import(self):
        """测试配置导入"""
        from admin.config import settings

        assert settings is not None
        assert settings.PORT == 8001

    def test_config_values(self):
        """测试配置值"""
        from admin.config import settings

        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.INTERNAL_SECRET == "test_secret"


class TestAdminModels:
    """测试管理员模型"""

    def test_admin_user_model(self):
        """测试管理员用户模型"""
        from admin.models import AdminUser

        assert AdminUser.__tablename__ == "admin_users"

    def test_admin_user_fields(self):
        """测试管理员用户模型字段"""
        from admin.models import AdminUser

        assert hasattr(AdminUser, "uid")
        assert hasattr(AdminUser, "email")
        assert hasattr(AdminUser, "password_hash")
        assert hasattr(AdminUser, "name")
        assert hasattr(AdminUser, "role")

    def test_admin_user_properties(self):
        """测试管理员用户模型属性"""
        from admin.models import AdminUser

        # 模拟对象
        admin = AdminUser(
            uid=12345,
            email="admin@example.com",
            password_hash="hash",
            name="Admin",
            role="super",
            status=1,
        )

        assert admin.is_active is True
        assert admin.is_super_admin is True

    def test_invitation_code_model(self):
        """测试邀请码模型"""
        from admin.models import InvitationCode

        assert InvitationCode.__tablename__ == "invitation_codes"

    def test_invitation_code_properties(self):
        """测试邀请码属性"""
        from admin.models import InvitationCode
        from datetime import datetime, timedelta

        # 有效的邀请码
        code = InvitationCode(
            code="TEST123",
            type="register",
            status=1,
            created_by=1,
            expires_at=datetime.now() + timedelta(days=7),
            max_uses=1,
            used_count=0,
        )

        assert code.is_valid is True
        assert code.is_used is False
        assert code.is_disabled is False


class TestAdminUtils:
    """测试管理员工具"""

    def test_password_strength_check(self):
        """测试密码强度检查"""
        from admin.utils.password import check_password_strength

        # 弱密码
        ok, msg = check_password_strength("weak")
        assert ok is False

        # 强密码
        ok, msg = check_password_strength("StrongPassword123!")
        assert ok is True


class TestAdminSchemas:
    """测试管理员 Pydantic 模型"""

    def test_admin_login_request(self):
        """测试管理员登录请求模型"""
        from admin.schemas import AdminLoginRequest

        req = AdminLoginRequest(
            email="admin@example.com",
            password="Password123!",
        )
        assert req.email == "admin@example.com"

    def test_generate_invitation_code_request(self):
        """测试生成邀请码请求模型"""
        from admin.schemas import GenerateInvitationCodeRequest

        req = GenerateInvitationCodeRequest(
            quantity=5,
            expires_days=7,
            max_uses=1,
        )
        assert req.quantity == 5
        assert req.expires_days == 7


class TestAdminServices:
    """测试管理员服务"""

    def test_auth_service_import(self):
        """测试认证服务导入"""
        from admin.services import AdminAuthService

        assert AdminAuthService is not None

    def test_invitation_service_import(self):
        """测试邀请码服务导入"""
        from admin.services import InvitationCodeService

        assert InvitationCodeService is not None

    def test_generate_code(self):
        """测试邀请码生成"""
        from admin.services import InvitationCodeService

        code = InvitationCodeService.generate_code(length=16)
        assert len(code) == 16


class TestAdminDependencies:
    """测试管理员依赖"""

    def test_dependencies_import(self):
        """测试依赖导入"""
        from admin.dependencies import get_current_admin, get_db_session

        assert get_current_admin is not None
        assert get_db_session is not None


class TestNewsModel:
    """测试新闻模型"""

    def test_news_model_import(self):
        """测试新闻模型导入"""
        from common.models.news import News

        assert News is not None
        assert News.__tablename__ == "news"

    def test_news_model_fields(self):
        """测试新闻模型字段"""
        from common.models.news import News

        # 检查字段存在
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
        """测试新闻模型属性"""
        from common.models.news import News
        from datetime import datetime

        # 模拟新闻对象
        news = News(
            uid=123456789,
            language="zh",
            title="测试新闻",
            slug="test-news",
            summary="测试摘要",
            cover_image="https://example.com/image.jpg",
            content="# 测试内容",
            status=1,
            published_at=datetime.now(),
            author_id=1,
        )

        assert news.is_published is True
        assert news.is_draft is False
        assert news.is_offline is False

        # 测试草稿状态
        news.status = 0
        assert news.is_draft is True

        # 测试下线状态
        news.status = 2
        assert news.is_offline is True


class TestNewsSchemas:
    """测试新闻 Pydantic 模型"""

    def test_create_news_request(self):
        """测试创建新闻请求模型"""
        from admin.schemas import CreateNewsRequest

        req = CreateNewsRequest(
            title="测试新闻",
            slug="test-news",
            language="zh",
            content="# 测试内容",
            status=1,
        )

        assert req.title == "测试新闻"
        assert req.slug == "test-news"
        assert req.language == "zh"
        assert req.status == 1

    def test_update_news_request(self):
        """测试更新新闻请求模型"""
        from admin.schemas import UpdateNewsRequest

        req = UpdateNewsRequest(
            title="更新后的标题",
            status=2,
        )

        assert req.title == "更新后的标题"
        assert req.status == 2

    def test_news_data(self):
        """测试新闻数据模型"""
        from admin.schemas import NewsData
        from datetime import datetime

        data = NewsData(
            uid=123456789,
            language="zh",
            title="测试新闻",
            slug="test-news",
            summary="测试摘要",
            cover_image="https://example.com/image.jpg",
            content="# 测试内容",
            status=1,
            published_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert data.uid == 123456789
        assert data.language == "zh"
        assert data.title == "测试新闻"


class TestNewsService:
    """测试新闻服务"""

    def test_news_service_import(self):
        """测试新闻服务导入"""
        from admin.services.news_service import NewsService

        assert NewsService is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
