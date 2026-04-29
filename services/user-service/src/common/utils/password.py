"""
密码工具模块
提供密码哈希、验证功能
使用 bcrypt 算法，安全性高
"""

from passlib.context import CryptContext

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
