"""
密码工具模块（api-service 用户域专用）
提供密码强度检查（基于服务配置）
"""

import re
from typing import Tuple

from app.core.config import settings


# 错误消息配置（支持国际化）
PASSWORD_ERROR_MESSAGES = {
    "zh": {
        "min_length": "密码必须至少{min_length}位",
        "uppercase": "密码必须包含至少一个大写字母",
        "lowercase": "密码必须包含至少一个小写字母",
        "digit": "密码必须包含至少一个数字",
        "special": "密码必须包含至少一个特殊字符",
        "strong": "密码强度符合要求",
    },
    "en": {
        "min_length": "Password must be at least {min_length} characters",
        "uppercase": "Password must contain at least one uppercase letter",
        "lowercase": "Password must contain at least one lowercase letter",
        "digit": "Password must contain at least one digit",
        "special": "Password must contain at least one special character",
        "strong": "Password strength meets requirements",
    },
}


def check_password_strength(password: str, lang: str = "zh") -> Tuple[bool, str]:
    """
    检查密码强度

    Args:
        password: 明文密码
        lang: 语言代码（"zh" 或 "en"，默认 "zh"）

    Returns:
        Tuple[bool, str]: (是否通过, 错误信息)
    """
    msgs = PASSWORD_ERROR_MESSAGES.get(lang, PASSWORD_ERROR_MESSAGES["zh"])

    # 检查最小长度
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, msgs["min_length"].format(min_length=settings.PASSWORD_MIN_LENGTH)

    # 检查大写字母
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, msgs["uppercase"]

    # 检查小写字母
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, msgs["lowercase"]

    # 检查数字
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return False, msgs["digit"]

    # 检查特殊字符
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        return False, msgs["special"]

    return True, msgs["strong"]
