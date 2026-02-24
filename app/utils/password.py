"""
密码工具模块
提供密码哈希、验证和强度检查功能
使用 bcrypt 算法，安全性高
"""

import re
from typing import Tuple

from passlib.context import CryptContext

from app.config import settings

# 创建密码上下文，使用 bcrypt 算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对密码进行 bcrypt 哈希

    Args:
        password: 明文密码

    Returns:
        str: bcrypt 哈希后的密码
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否匹配哈希密码

    Args:
        plain_password: 明文密码
        hashed_password: bcrypt 哈希后的密码

    Returns:
        bool: 是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def check_password_strength(password: str) -> Tuple[bool, str]:
    """
    检查密码强度

    根据配置的要求检查密码：
    - 最小长度
    - 必须包含大写字母
    - 必须包含小写字母
    - 必须包含数字
    - 必须包含特殊字符

    Args:
        password: 明文密码

    Returns:
        Tuple[bool, str]: (是否通过, 错误信息)

    Example:
        >>> ok, msg = check_password_strength("Weak123")
        >>> print(ok, msg)
        False "密码必须至少8位"

        >>> ok, msg = check_password_strength("Strong@123")
        >>> print(ok, msg)
        True "密码强度符合要求"
    """
    # 检查最小长度
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"密码必须至少{settings.PASSWORD_MIN_LENGTH}位"

    # 检查大写字母
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, "密码必须包含至少一个大写字母"

    # 检查小写字母
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, "密码必须包含至少一个小写字母"

    # 检查数字
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return False, "密码必须包含至少一个数字"

    # 检查特殊字符
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        return False, "密码必须包含至少一个特殊字符"

    return True, "密码强度符合要求"


def get_password_strength_level(password: str) -> int:
    """
    获取密码强度等级（0-4）

    用于前端显示密码强度条

    Args:
        password: 明文密码

    Returns:
        int: 强度等级 0=弱 1=较弱 2=中等 3=较强 4=强
    """
    if not password:
        return 0

    score = 0

    # 长度加分
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1

    # 字符类型加分
    if re.search(r"[a-z]", password) and re.search(r"[A-Z]", password):
        score += 1

    if re.search(r"\d", password):
        score += 1

    if re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        score += 1

    # 归一化到 0-4
    if score <= 2:
        return 1
    elif score <= 4:
        return 2
    elif score <= 5:
        return 3
    else:
        return 4


# 密码黑名单（常见弱密码）
PASSWORD_BLACKLIST = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "password123", "admin", "letmein", "welcome", "monkey",
}


def is_common_password(password: str) -> bool:
    """
    检查是否是常见弱密码

    Args:
        password: 明文密码

    Returns:
        bool: 是否是常见密码
    """
    return password.lower() in PASSWORD_BLACKLIST
