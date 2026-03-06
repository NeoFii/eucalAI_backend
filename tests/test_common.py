"""
Common 模块单元测试
测试共享的工具和基础功能
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


class TestExceptions:
    """测试异常类"""

    def test_exception_base(self):
        """测试基础异常"""
        from common.core.exceptions import APIException

        exc = APIException(status_code=400, detail="测试错误")
        assert exc.detail == "测试错误"
        assert exc.status_code == 400

    def test_auth_exception(self):
        """测试认证异常"""
        from common.core.exceptions import AuthenticationException

        exc = AuthenticationException(detail="测试错误")
        assert exc.detail == "测试错误"

    def test_invalid_credentials(self):
        """测试无效凭证异常"""
        from common.core.exceptions import InvalidCredentialsException

        exc = InvalidCredentialsException()
        assert exc.detail is not None

    def test_token_exceptions(self):
        """测试 Token 相关异常"""
        from common.core.exceptions import (
            InvalidTokenException,
            TokenExpiredException,
        )

        exc1 = InvalidTokenException()
        assert exc1.detail is not None

        exc2 = TokenExpiredException()
        assert exc2.detail is not None


class TestTimezoneUtils:
    """测试时区工具"""

    def test_now(self):
        """测试当前时间"""
        from common.utils.timezone import now

        t = now()
        assert t is not None

    def test_now_with_tz(self):
        """测试带时区的当前时间"""
        from common.utils.timezone import now_with_tz

        t = now_with_tz()
        assert t is not None
        assert t.tzinfo is not None

    def test_format_iso(self):
        """测试 ISO 格式化"""
        from datetime import datetime
        from common.utils.timezone import format_iso

        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = format_iso(dt)
        assert "2024" in result


class TestSnowflakeUtils:
    """测试雪花 ID 生成"""

    def test_generate_snowflake_id(self):
        """测试生成雪花 ID"""
        from common.utils.snowflake import generate_snowflake_id

        # 配置雪花 ID
        from common.utils.snowflake import configure_snowflake
        configure_snowflake(worker_id=1, datacenter_id=1)

        ids = [generate_snowflake_id() for _ in range(10)]
        # 确保生成的 ID 都是唯一的
        assert len(set(ids)) == 10

    def test_snowflake_id_type(self):
        """测试雪花 ID 类型"""
        from common.utils.snowflake import generate_snowflake_id, configure_snowflake

        configure_snowflake(worker_id=1, datacenter_id=1)
        uid = generate_snowflake_id()

        assert isinstance(uid, int)
        assert uid > 0


class TestPasswordUtils:
    """测试密码工具"""

    def test_hash_and_verify(self):
        """测试密码哈希和验证"""
        from common.utils.password import hash_password, verify_password

        password = "TestPassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_hash_consistency(self):
        """测试哈希一致性（同一密码生成不同哈希）"""
        from common.utils.password import hash_password

        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # bcrypt 每次生成不同的盐，所以哈希不同
        assert hash1 != hash2
        # 但两者都能验证通过
        from common.utils.password import verify_password
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestJWTUtils:
    """测试 JWT 工具"""

    def test_create_access_token(self):
        """测试创建访问令牌"""
        from common.utils.jwt import create_access_token, decode_token

        data = {"uid": 12345, "sub": "12345"}
        token = create_access_token(
            data=data,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
            expire_minutes=15,
        )

        assert token is not None
        assert isinstance(token, str)

        # 解码验证
        payload = decode_token(
            token=token,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        )

        assert payload is not None
        assert payload["uid"] == 12345
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        """测试创建刷新令牌"""
        from common.utils.jwt import create_refresh_token, decode_token

        data = {"uid": 12345}
        token = create_refresh_token(
            data=data,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
            expire_days=7,
        )

        assert token is not None

        payload = decode_token(
            token=token,
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        )

        assert payload is not None
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        """测试解码无效令牌"""
        from common.utils.jwt import decode_token

        result = decode_token(
            token="invalid_token",
            secret_key="test_secret_key_for_jwt_32bytes!",
            algorithm="HS256",
        )

        assert result is None

    def test_get_token_jti(self):
        """测试获取令牌 JTI"""
        from common.utils.jwt import create_access_token, get_token_jti

        token = create_access_token(
            data={"uid": 12345},
            secret_key="test_secret_key_for_jwt_32bytes!",
            expire_minutes=15,
        )

        jti = get_token_jti(token)
        assert jti is not None
        assert isinstance(jti, str)
        assert len(jti) == 64  # SHA256 十六进制


class TestDatabase:
    """测试数据库模块"""

    def test_database_imports(self):
        """测试数据库模块导入"""
        from common.db import (
            Base,
            close_db,
            create_engine,
            get_db,
            get_db_context,
            init_db,
            init_session_factory,
        )

        assert Base is not None
        assert create_engine is not None
        assert get_db is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
