"""JWT 工具模块
提供 JWT 令牌的签发、验证和解码功能

注意：JWT 的 exp 和 iat 字段必须使用 UTC 时间（JWT 国际标准规范）
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt


def create_access_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None,
    expire_minutes: int = 15,
) -> str:
    """
    创建访问令牌（access_token）

    注意：JWT 的 exp 必须使用 UTC 时间戳（国际标准）

    Args:
        data: 要编码的数据（通常包含用户 uid）
        secret_key: JWT 密钥
        algorithm: 签名算法
        expires_delta: 自定义过期时间，默认使用 expire_minutes
        expire_minutes: 默认过期分钟数

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    # JWT exp 必须使用 UTC 时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # 签发时间也使用 UTC
        "type": "access",  # 令牌类型
    })

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def get_token_jti(token: str) -> str:
    """
    计算令牌的 JTI（JWT ID）

    使用 SHA256 哈希生成唯一标识符，用于数据库索引和快速查找。

    Args:
        token: JWT 令牌字符串

    Returns:
        str: SHA256 哈希值（前 64 个字符）
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_refresh_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None,
    expire_days: int = 7,
) -> str:
    """
    创建刷新令牌（refresh_token）

    注意：JWT 的 exp 必须使用 UTC 时间戳（国际标准）

    Args:
        data: 要编码的数据（通常包含 session_id）
        secret_key: JWT 密钥
        algorithm: 签名算法
        expires_delta: 自定义过期时间，默认使用 expire_days
        expire_days: 默认过期天数

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    # JWT exp 必须使用 UTC 时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=expire_days)

    # 先生成基础令牌（不含 jti）
    base_payload = to_encode.copy()
    base_payload.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # 签发时间也使用 UTC
        "type": "refresh",
    })

    # 编码获取临时令牌以计算 jti
    temp_token = jwt.encode(base_payload, secret_key, algorithm=algorithm)

    # 计算 jti（令牌的 SHA256 哈希）
    token_jti = get_token_jti(temp_token)

    # 添加 jti 到 payload 并重新编码
    base_payload["jti"] = token_jti

    return jwt.encode(base_payload, secret_key, algorithm=algorithm)


def decode_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """
    解码并验证 JWT 令牌

    Args:
        token: JWT 令牌字符串
        secret_key: JWT 密钥
        algorithm: 签名算法

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except JWTError:
        return None


def verify_access_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """
    验证访问令牌

    检查：
    1. 令牌是否有效
    2. 令牌类型是否为 access

    Args:
        token: JWT 令牌字符串
        secret_key: JWT 密钥
        algorithm: 签名算法

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    payload = decode_token(token, secret_key, algorithm)
    if payload is None:
        return None

    # 检查令牌类型
    if payload.get("type") != "access":
        return None

    return payload


def verify_refresh_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """
    验证刷新令牌

    检查：
    1. 令牌是否有效
    2. 令牌类型是否为 refresh

    Args:
        token: JWT 令牌字符串
        secret_key: JWT 密钥
        algorithm: 签名算法

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    payload = decode_token(token, secret_key, algorithm)
    if payload is None:
        return None

    # 检查令牌类型
    if payload.get("type") != "refresh":
        return None

    return payload
