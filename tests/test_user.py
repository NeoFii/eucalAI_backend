"""
User 模块单元测试
测试用户服务的配置、模型、工具等
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


class TestUserConfig:
    """测试用户服务配置"""

    def test_config_import(self):
        """测试配置导入"""
        from user.config import settings

        assert settings is not None
        assert settings.PORT == 8000
        assert settings.JWT_ALGORITHM == "HS256"

    def test_config_values(self):
        """测试配置值"""
        from user.config import settings

        assert settings.PORT == 8000
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.ADMIN_SERVICE_URL == "http://localhost:8001"


class TestUserModels:
    """测试用户模型"""

    def test_user_model_import(self):
        """测试用户模型导入"""
        from user.models import User

        assert User.__tablename__ == "users"

    def test_user_model_fields(self):
        """测试用户模型字段"""
        from user.models import User

        # 检查主要字段存在
        assert hasattr(User, "uid")
        assert hasattr(User, "email")
        assert hasattr(User, "password_hash")
        assert hasattr(User, "status")

    def test_user_model_properties(self):
        """测试用户模型属性"""
        from user.models import User

        # 创建模拟对象
        user = User(
            uid=12345,
            email="test@example.com",
            password_hash="hash",
            status=1,
        )

        assert user.is_active is True
        assert user.is_email_verified is False

    def test_user_session_model(self):
        """测试用户会话模型"""
        from user.models import UserSession

        assert UserSession.__tablename__ == "user_sessions"


class TestUserUtils:
    """测试用户工具"""

    def test_password_strength_check(self):
        """测试密码强度检查"""
        from user.utils.password import check_password_strength

        # 弱密码
        ok, msg = check_password_strength("weak")
        assert ok is False

        # 强密码
        ok, msg = check_password_strength("StrongPassword123!")
        assert ok is True

    def test_admin_client_import(self):
        """测试管理员客户端导入"""
        from user.utils import verify_and_use_invitation_code, get_invitation_code_stats

        assert verify_and_use_invitation_code is not None
        assert get_invitation_code_stats is not None


class TestUserSchemas:
    """测试用户 Pydantic 模型"""

    def test_login_request(self):
        """测试登录请求模型"""
        from user.schemas import LoginRequest

        req = LoginRequest(email="test@example.com", password="password123")
        assert req.email == "test@example.com"
        assert req.password == "password123"

    def test_register_request(self):
        """测试注册请求模型"""
        from user.schemas import RegisterRequest

        # 这个测试需要满足密码强度要求
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
        """测试用户信息响应模型"""
        from user.schemas import UserInfoResponseData
        from datetime import datetime

        data = UserInfoResponseData(
            uid=12345,
            email="test@example.com",
            status=1,
            created_at=datetime.now(),
        )
        assert data.uid == 12345
        assert data.status == 1


class TestUserServices:
    """测试用户服务"""

    def test_auth_service_import(self):
        """测试认证服务导入"""
        from user.services import AuthService

        assert AuthService is not None

    def test_email_service_import(self):
        """测试邮箱服务导入"""
        from user.services import email_service

        assert email_service is not None


class TestUserAPI:
    """测试用户 API"""

    def test_dependencies_import(self):
        """测试依赖导入"""
        from user.dependencies import (
            get_current_user,
            get_db_session,
            get_optional_user,
        )

        assert get_current_user is not None
        assert get_db_session is not None


class TestNewsPublicAPI:
    """测试新闻公开 API"""

    def test_news_router_import(self):
        """测试新闻路由导入"""
        from user.api.v1.endpoints.news import router

        assert router is not None
        assert router.tags == ["新闻"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
