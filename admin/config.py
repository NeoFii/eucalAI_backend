"""
管理员服务配置
继承并扩展公共配置基类
"""

from functools import lru_cache
from typing import List, Union

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """
    管理员服务配置类
    """

    # 覆盖项目信息
    PROJECT_NAME: str = "Eucal AI 管理员服务"
    DESCRIPTION: str = "Eucal AI 管理员服务 API"

    # 覆盖端口
    PORT: int = 8001

    # 覆盖 CORS（管理后台额外允许 3001 端口）
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    # 内部 API 前缀
    INTERNAL_API_PREFIX: str = "/internal"

    # 覆盖 Cookie 配置（管理后台使用宽松策略）
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # 覆盖雪花 ID 配置（各服务使用不同 worker_id 避免冲突）
    SNOWFLAKE_WORKER_ID: int = 2

    # 覆盖 JWT 过期时间（管理后台 access token 有效期更长）
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # 覆盖日志前缀
    LOG_FILE_PREFIX: str = "admin"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
