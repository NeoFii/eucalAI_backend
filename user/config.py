"""
用户服务配置
继承并扩展公共配置基类
"""

from functools import lru_cache

from common.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """
    用户服务配置类
    """

    # 覆盖项目信息
    PROJECT_NAME: str = "Eucal AI 用户服务"
    DESCRIPTION: str = "Eucal AI 用户服务 API"

    # 覆盖端口
    PORT: int = 8000

    # 覆盖雪花 ID 配置（各服务使用不同 worker_id 避免冲突）
    SNOWFLAKE_WORKER_ID: int = 1

    # 覆盖日志前缀
    LOG_FILE_PREFIX: str = "user"

    # 管理员服务配置（内部调用）
    ADMIN_SERVICE_URL: str = "http://localhost:8001"

    # 邮箱验证码配置
    EMAIL_CODE_EXPIRE_MINUTES: int = 5

    # SMTP 邮件配置
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM: str = "Eucal AI"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
