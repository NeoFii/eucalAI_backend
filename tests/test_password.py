"""
密码工具模块测试
测试密码哈希、验证和强度检查功能
"""

import pytest
from app.utils.password import (
    hash_password,
    verify_password,
    check_password_strength,
    get_password_strength_level,
    is_common_password,
    PASSWORD_BLACKLIST,
)


class TestHashPassword:
    """密码哈希测试"""

    def test_hash_password_returns_string(self):
        """测试哈希返回字符串"""
        hashed = hash_password("Test1234!")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_unique(self):
        """测试相同密码生成不同哈希（bcrypt salt）"""
        password = "Test1234!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # bcrypt 自动生成唯一 salt

    def test_hash_different_passwords(self):
        """测试不同密码生成不同哈希"""
        hash1 = hash_password("Password1!")
        hash2 = hash_password("Password2!")
        assert hash1 != hash2


class TestVerifyPassword:
    """密码验证测试"""

    def test_verify_correct_password(self):
        """测试正确密码验证成功"""
        password = "Test1234!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """测试错误密码验证失败"""
        password = "Test1234!"
        wrong_password = "Wrong1234!"
        hashed = hash_password(password)
        assert verify_password(wrong_password, hashed) is False

    def test_verify_empty_password(self):
        """测试空密码验证"""
        hashed = hash_password("Test1234!")
        assert verify_password("", hashed) is False


class TestCheckPasswordStrength:
    """密码强度检查测试"""

    def test_password_strength_valid(self):
        """测试有效密码通过检查"""
        ok, msg = check_password_strength("Test1234!")
        assert ok is True
        assert msg == "密码强度符合要求"

    def test_password_too_short(self):
        """测试密码太短"""
        ok, msg = check_password_strength("Tes1!")
        assert ok is False
        assert "密码必须至少8位" in msg

    def test_password_no_uppercase(self):
        """测试缺少大写字母"""
        ok, msg = check_password_strength("test1234!")
        assert ok is False
        assert "大写字母" in msg

    def test_password_no_lowercase(self):
        """测试缺少小写字母"""
        ok, msg = check_password_strength("TEST1234!")
        assert ok is False
        assert "小写字母" in msg

    def test_password_no_digit(self):
        """测试缺少数字"""
        ok, msg = check_password_strength("Testabcd!")
        assert ok is False
        assert "数字" in msg

    def test_password_no_special(self):
        """测试缺少特殊字符"""
        ok, msg = check_password_strength("Test1234")
        assert ok is False
        assert "特殊字符" in msg

    def test_password_exactly_min_length(self):
        """测试刚好最小长度"""
        ok, msg = check_password_strength("Test123!")
        assert ok is True

    def test_password_very_long(self):
        """测试较长密码"""
        # 包含所有类型的字符
        long_password = "Aa" + "B" * 38 + "1!"
        ok, msg = check_password_strength(long_password)
        assert ok is True


class TestGetPasswordStrengthLevel:
    """密码强度等级测试"""

    def test_empty_password_level(self):
        """测试空密码强度等级"""
        level = get_password_strength_level("")
        assert level == 0

    def test_very_weak_password(self):
        """测试非常弱的密码"""
        level = get_password_strength_level("a")
        assert level == 1

    def test_weak_password(self):
        """测试弱密码"""
        level = get_password_strength_level("password")
        assert 0 <= level <= 4

    def test_medium_password(self):
        """测试中等强度密码"""
        level = get_password_strength_level("Password1")
        assert 0 <= level <= 4

    def test_strong_password(self):
        """测试强密码"""
        level = get_password_strength_level("Str0ng@P4ssw0rd!")
        assert level >= 3

    def test_very_long_strong_password(self):
        """测试超长强密码"""
        level = get_password_strength_level("VeryStr0ng@P4ssw0rd!2024VeryStr0ng@P4ssw0rd!2024")
        assert level >= 3


class TestIsCommonPassword:
    """常见密码检查测试"""

    def test_common_password_in_blacklist(self):
        """测试黑名单中的密码"""
        for common_password in PASSWORD_BLACKLIST:
            assert is_common_password(common_password) is True
            assert is_common_password(common_password.upper()) is True
            assert is_common_password(common_password + "1") is False

    def test_not_common_password(self):
        """测试非常见密码"""
        assert is_common_password("UniquePass123!") is False
        assert is_common_password("MySecret@2024") is False

    def test_similar_to_common_password(self):
        """测试与常见密码相似但不同的密码"""
        assert is_common_password("password123") is True
        assert is_common_password("passw0rd") is False
        assert is_common_password("1234567") is False


class TestPasswordIntegration:
    """密码功能集成测试"""

    def test_hash_and_verify_integration(self):
        """测试哈希和验证集成"""
        original_password = "MyStr0ng@Pass"

        # 哈希密码
        hashed = hash_password(original_password)

        # 验证正确密码
        assert verify_password(original_password, hashed) is True

        # 验证错误密码
        assert verify_password("WrongPassword", hashed) is False

    def test_password_strength_and_verify_integration(self):
        """测试密码强度和验证集成"""
        test_cases = [
            ("Abc1234!", True),    # 强密码 (8位)
            ("weak", False),       # 太短
            ("12345678", False),   # 缺少字母和特殊字符
            ("PASSWORD1!", False), # 缺少小写字母
        ]

        for password, expected_strength in test_cases:
            ok, _ = check_password_strength(password)
            assert ok == expected_strength
