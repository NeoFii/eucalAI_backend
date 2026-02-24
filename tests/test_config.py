"""
配置模块单元测试
测试配置加载和验证
"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestSettingsValidation:
    """测试配置验证"""

    def test_settings_requires_jwt_secret_key(self):
        """测试 JWT_SECRET_KEY 必须配置"""
        # 注意：实际测试时需要 mock 环境变量
        pass

    def test_settings_requires_database_url(self):
        """测试 DATABASE_URL 必须配置"""
        pass


class TestAllowedHostsParsing:
    """测试 ALLOWED_HOSTS 解析"""

    @pytest.mark.asyncio
    async def test_allowed_hosts_as_list(self):
        """测试列表格式的 ALLOWED_HOSTS"""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "ALLOWED_HOSTS": '["http://localhost:3000", "http://localhost:5173"]',
        }):
            # 重新加载配置
            from app.config import Settings

            settings = Settings(_env_file=".env")
            assert isinstance(settings.ALLOWED_HOSTS, list)
            assert "http://localhost:3000" in settings.ALLOWED_HOSTS

    @pytest.mark.asyncio
    async def test_allowed_hosts_as_comma_separated(self):
        """测试逗号分隔的 ALLOWED_HOSTS"""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "ALLOWED_HOSTS": "http://localhost:3000,http://localhost:5173",
        }):
            from app.config import Settings

            settings = Settings(_env_file=".env")
            assert isinstance(settings.ALLOWED_HOSTS, list)
            assert "http://localhost:3000" in settings.ALLOWED_HOSTS

    @pytest.mark.asyncio
    async def test_allowed_hosts_as_single_value(self):
        """测试单个值的 ALLOWED_HOSTS"""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "ALLOWED_HOSTS": "http://localhost:3000",
        }):
            from app.config import Settings

            settings = Settings(_env_file=".env")
            assert isinstance(settings.ALLOWED_HOSTS, list)
            assert "http://localhost:3000" in settings.ALLOWED_HOSTS


class TestConfigDefaults:
    """测试配置默认值"""

    def test_default_values(self):
        """测试默认配置值"""
        # 测试默认值（需要在没有环境变量的情况下测试）
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        }, clear=False):
            from app.config import Settings

            settings = Settings(_env_file=".env")
            assert settings.PROJECT_NAME == "Eucal AI 官网 API"
            assert settings.VERSION == "0.1.0"
            assert settings.DEBUG is True
            assert settings.JWT_ALGORITHM == "HS256"
            assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 15
            assert settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 7
            assert settings.PASSWORD_MIN_LENGTH == 8
            assert settings.PASSWORD_REQUIRE_UPPERCASE is True
            assert settings.PASSWORD_REQUIRE_LOWERCASE is True
            assert settings.PASSWORD_REQUIRE_DIGIT is True
            assert settings.PASSWORD_REQUIRE_SPECIAL is True
            assert settings.EMAIL_CODE_EXPIRE_MINUTES == 5


class TestConfigSingleton:
    """测试配置单例"""

    def test_get_settings_returns_same_instance(self):
        """测试 get_settings 返回相同实例"""
        from app.config import get_settings, Settings

        # 需要确保环境变量存在
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        }):
            # 清除缓存
            get_settings.cache_clear()

            settings1 = get_settings()
            settings2 = get_settings()

            assert settings1 is settings2


class TestPasswordConfig:
    """测试密码配置"""

    def test_password_config_values(self):
        """测试密码相关配置"""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "PASSWORD_MIN_LENGTH": "12",
            "PASSWORD_REQUIRE_UPPERCASE": "false",
            "PASSWORD_REQUIRE_LOWERCASE": "false",
            "PASSWORD_REQUIRE_DIGIT": "false",
            "PASSWORD_REQUIRE_SPECIAL": "false",
        }):
            from app.config import Settings

            settings = Settings(_env_file=".env")
            assert settings.PASSWORD_MIN_LENGTH == 12
            assert settings.PASSWORD_REQUIRE_UPPERCASE is False
            assert settings.PASSWORD_REQUIRE_LOWERCASE is False
            assert settings.PASSWORD_REQUIRE_DIGIT is False
            assert settings.PASSWORD_REQUIRE_SPECIAL is False
