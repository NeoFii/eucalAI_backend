"""
密码强度检查工具
用于验证管理员密码强度
"""

import re
from typing import Tuple

from admin.config import settings


def check_password_strength(password: str) -> Tuple[bool, str]:
    """
    检查密码强度

    Args:
        password: 待检查的密码

    Returns:
        Tuple[bool, str]: (是否通过, 错误消息)
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"密码长度至少 {settings.PASSWORD_MIN_LENGTH} 位"

    if settings.PASSWORD_REQUIRE_UPPERCASE:
        if not re.search(r"[A-Z]", password):
            return False, "密码必须包含大写字母"

    if settings.PASSWORD_REQUIRE_LOWERCASE:
        if not re.search(r"[a-z]", password):
            return False, "密码必须包含小写字母"

    if settings.PASSWORD_REQUIRE_DIGIT:
        if not re.search(r"\d", password):
            return False, "密码必须包含数字"

    if settings.PASSWORD_REQUIRE_SPECIAL:
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "密码必须包含特殊字符"

    return True, ""
