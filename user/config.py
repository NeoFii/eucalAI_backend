"""
用户服务配置
继承并扩展基础配置
"""

from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    用户服务配置类
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 项目信息
    PROJECT_NAME: str = "Eucal AI 用户服务"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Eucal AI 用户服务 API"

    # API 配置
    API_V1_PREFIX: str = "/api/v1"
    PORT: int = 8000

    # 环境配置
    DEBUG: bool = False

    # CORS 配置
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    PRODUCTION_ALLOWED_HOSTS: Union[str, List[str]] = []

    # 管理员服务配置（内部调用）
    ADMIN_SERVICE_URL: str = "http://localhost:8001"
    INTERNAL_SECRET: str = ""  # 内部 API 调用密钥

    # 时区设置
    TIMEZONE: str = "Asia/Shanghai"

    # 数据库配置
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # JWT 配置
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_SECRET_KEY_MIN_LENGTH: int = 32

    # Cookie 配置
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "strict"

    # 雪花 ID 配置
    SNOWFLAKE_WORKER_ID: int = 1
    SNOWFLAKE_DATACENTER_ID: int = 1

    # 密码安全配置
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # 邮箱验证码配置
    EMAIL_CODE_EXPIRE_MINUTES: int = 5

    # SMTP 邮件配置
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM: str = "Eucal AI"

    # 日志配置
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    LOG_MAX_DAYS: int = 30
    LOG_FILE_PREFIX: str = "user"

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        """解析 CORS 主机列表"""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                import json
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            return [host.strip() for host in v.split(",") if host.strip()]
        return ["http://localhost:5173", "http://localhost:3000"]

    @model_validator(mode="after")
    def validate_required_fields(self) -> "Settings":
        """验证并初始化配置字段"""
        import secrets
        import warnings

        # JWT_SECRET_KEY 处理
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in ["your-secret-key", ""]:
            self.JWT_SECRET_KEY = secrets.token_hex(32)
            warnings.warn(
                "JWT_SECRET_KEY 未配置，已自动生成随机密钥。",
                UserWarning,
            )

        if len(self.JWT_SECRET_KEY) < self.JWT_SECRET_KEY_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY 长度必须至少 {self.JWT_SECRET_KEY_MIN_LENGTH} 位！"
            )

        # INTERNAL_SECRET 检查
        if not self.INTERNAL_SECRET:
            raise ValueError("INTERNAL_SECRET 必须配置！用于服务间安全调用。")

        return self

    @property
    def cors_allowed_hosts(self) -> List[str]:
        """获取当前环境适用的 CORS 允许域名列表"""
        if not self.DEBUG and self.PRODUCTION_ALLOWED_HOSTS:
            if isinstance(self.PRODUCTION_ALLOWED_HOSTS, str):
                return [h.strip() for h in self.PRODUCTION_ALLOWED_HOSTS.split(",") if h.strip()]
            return self.PRODUCTION_ALLOWED_HOSTS
        if isinstance(self.ALLOWED_HOSTS, str):
            return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]
        return self.ALLOWED_HOSTS


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
