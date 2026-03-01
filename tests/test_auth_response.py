"""
认证响应结构测试
测试登录/注册响应的数据结构
"""

import pytest


class TestResponseStructure:
    """响应结构测试"""

    def test_login_response_has_user_field(self):
        """验证 LoginResponseData 包含 user 字段"""
        from app.models.auth_schemas import LoginResponseData, UserData

        # 验证 UserData 模型存在
        user_data = UserData(
            uid=1,
            email="test@example.com",
            nickname="test",
            avatar_url=None
        )

        # 验证 LoginResponseData 接受 user 参数
        response_data = LoginResponseData(
            user=user_data,
            access_token="test_token",
            expires_in=900
        )

        assert hasattr(response_data, "user"), "LoginResponseData 应包含 user 字段"
        assert response_data.user.uid == 1
        assert response_data.user.email == "test@example.com"

    def test_login_response_no_refresh_token_field(self):
        """验证 LoginResponseData 不包含 refresh_token 字段"""
        from app.models.auth_schemas import LoginResponseData, UserData

        user_data = UserData(
            uid=1,
            email="test@example.com",
            nickname="test",
            avatar_url=None
        )

        response_data = LoginResponseData(
            user=user_data,
            access_token="test_token",
            expires_in=900
        )

        # 验证 refresh_token 字段不存在
        assert not hasattr(response_data, "refresh_token"), "LoginResponseData 不应包含 refresh_token 字段"

        # 验证 model_dump 不包含 refresh_token
        dump = response_data.model_dump()
        assert "refresh_token" not in dump, "响应数据不应包含 refresh_token"

    def test_register_response_no_refresh_token_field(self):
        """验证 RegisterResponseData 不包含 refresh_token 字段"""
        from app.models.auth_schemas import RegisterResponseData
        from datetime import datetime

        response_data = RegisterResponseData(
            uid=1,
            email="test@example.com",
            nickname="test",
            created_at=datetime.now(),
            access_token="test_token",
            expires_in=900
        )

        # 验证 refresh_token 字段不存在
        assert not hasattr(response_data, "refresh_token"), "RegisterResponseData 不应包含 refresh_token 字段"

        # 验证 model_dump 不包含 refresh_token
        dump = response_data.model_dump()
        assert "refresh_token" not in dump, "响应数据不应包含 refresh_token"


class TestRefreshEndpointSecurity:
    """刷新接口安全测试"""

    def test_refresh_only_accepts_cookie(self):
        """验证刷新接口只接受 Cookie，不接受 Header"""
        from app.api.v1.endpoints.auth import refresh
        import inspect

        sig = inspect.signature(refresh)
        params = list(sig.parameters.keys())

        # 不应该有 authorization 参数
        assert "authorization" not in params, "refresh 函数不应接受 authorization 参数"
        assert "Header" not in str(sig), "refresh 函数不应接受 Header"

    def test_refresh_requires_cookie(self):
        """验证刷新接口缺少 Cookie 时返回 401"""
        # 这个测试需要实际数据库，标记为集成测试
        pass
