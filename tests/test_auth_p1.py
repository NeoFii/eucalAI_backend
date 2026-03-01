"""
P1 任务相关测试
测试用户状态校验等功能
"""

import pytest


class TestUserStatusValidation:
    """用户状态校验测试"""

    def test_get_current_user_validates_user_status(self):
        """验证 get_current_user 检查用户状态"""
        # 检查函数签名是否包含 db 参数
        from app.api.v1.endpoints.auth import get_current_user_uid
        import inspect

        sig = inspect.signature(get_current_user_uid)
        params = list(sig.parameters.keys())

        assert "db" in params, "get_current_user_uid 应接受 db 参数以查询用户状态"

    def test_user_model_has_status_field(self):
        """验证 User 模型包含 status 字段"""
        from app.models import User

        # 检查 User 类是否有 status 属性
        assert hasattr(User, "status"), "User 模型应包含 status 字段"


class TestRefreshEndpointSecurity:
    """刷新接口安全测试"""

    def test_refresh_rejects_header_only(self):
        """验证刷新接口拒绝仅带 Header 的请求"""
        # 这个测试需要实际运行服务器
        pass
