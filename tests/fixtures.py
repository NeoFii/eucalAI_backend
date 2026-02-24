"""
测试工具模块
提供测试中使用的辅助函数
"""

import random
import string


def generate_random_email() -> str:
    """生成随机邮箱地址"""
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{username}@example.com"


def generate_random_password(length: int = 12) -> str:
    """生成随机密码（符合强度要求）"""
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=length))
    # 确保包含大小写字母和数字
    if not any(c.isupper() for c in password):
        password = "A" + password[1:]
    if not any(c.islower() for c in password):
        password = password[0] + "a" + password[2:]
    if not any(c.isdigit() for c in password):
        password = password[:-1] + "1"
    return password


def generate_verification_code() -> str:
    """生成6位随机验证码"""
    return ''.join(random.choices(string.digits, k=6))
