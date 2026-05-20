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
    """创建访问令牌（access_token），exp 使用 UTC 时间戳。"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    })

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def get_token_jti(token: str) -> str:
    """计算令牌的唯一标识符，用于数据库索引和会话查找。"""
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
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=expire_days)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    })

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """解码并验证 JWT 令牌，验证失败返回 None。"""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except JWTError:
        return None


def verify_access_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """验证访问令牌（检查签名 + type=access）。"""
    payload = decode_token(token, secret_key, algorithm)
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def verify_refresh_token(token: str, secret_key: str, algorithm: str = "HS256") -> Optional[dict]:
    """验证刷新令牌（检查签名 + type=refresh）。"""
    payload = decode_token(token, secret_key, algorithm)
    if payload is None:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload
