"""
应用配置管理
使用 Pydantic Settings 管理环境变量
"""

import json
import secrets
from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    从环境变量读取配置，支持 .env 文件
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 项目信息
    PROJECT_NAME: str = "Eucal AI 官网 API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Eucal AI 官网后端 API 服务"

    # API 配置
    API_V1_PREFIX: str = "/api/v1"

    # 环境配置
    DEBUG: bool = False  # 生产环境必须设为 False

    # CORS 配置 - 前后端分离，允许前端域名访问
    # 开发环境
    ALLOWED_HOSTS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    # 生产环境域名列表（DEBUG=False 时使用）
    PRODUCTION_ALLOWED_HOSTS: Union[str, List[str]] = []

    # 时区设置
    TIMEZONE: str = "Asia/Shanghai"

    # 数据库配置
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False  # 是否打印 SQL 语句（调试用）

    # JWT 配置
    JWT_SECRET_KEY: str = ""  # 生产环境必须设置！建议使用 openssl rand -hex 32 生成 64 位密钥
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # access_token 有效期 15 分钟
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # refresh_token 有效期 7 天
    JWT_SECRET_KEY_MIN_LENGTH: int = 32  # 密钥最小长度

    # Cookie 配置
    COOKIE_SECURE: bool = True  # 生产环境必须设为 True（HTTPS）
    COOKIE_SAMESITE: str = "strict"  # 生产环境建议设为 strict

    # 雪花 ID 配置
    SNOWFLAKE_WORKER_ID: int = 1  # 工作节点 ID（0-31）
    SNOWFLAKE_DATACENTER_ID: int = 1  # 数据中心 ID（0-31）

    # 密码安全配置
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # 邮箱验证码配置
    EMAIL_CODE_EXPIRE_MINUTES: int = 5  # 验证码有效期（分钟）

    # SMTP 邮件配置
    SMTP_HOST: str = ""  # SMTP 服务器地址
    SMTP_PORT: int = 587  # SMTP 端口
    SMTP_USER: str = ""  # SMTP 用户名
    SMTP_PASSWORD: str = ""  # SMTP 密码
    SMTP_TLS: bool = True  # 是否使用 TLS
    SMTP_FROM: str = "Eucal AI"  # 发件人名称

    # 日志配置
    LOG_DIR: str = "logs"  # 日志目录
    LOG_LEVEL: str = "INFO"  # 日志级别
    LOG_MAX_DAYS: int = 30  # 日志保留天数
    LOG_FILE_PREFIX: str = "app"  # 日志文件前缀

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        """解析 CORS 主机列表"""
        # 如果已经是列表
        if isinstance(v, list):
            return v
        # 如果是 JSON 格式的数组字符串
        if isinstance(v, str):
            # 尝试解析为 JSON
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # 尝试逗号分隔
            return [host.strip() for host in v.split(",") if host.strip()]
        return ["http://localhost:5173", "http://localhost:3000"]

    @model_validator(mode="after")
    def validate_required_fields(self) -> "Settings":
        """验证并初始化配置字段"""
        # JWT_SECRET_KEY 处理：未配置或示例值时自动生成
        example_keys = ["your-secret-key-change-in-production", "your-secret-key", ""]
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in example_keys:
            # 自动生成 64 位随机密钥
            self.JWT_SECRET_KEY = secrets.token_hex(32)
            import warnings

            warnings.warn(
                "JWT_SECRET_KEY 未配置，已自动生成随机密钥。"
                "注意：每次重启服务密钥都会变化，所有现有登录会话将失效！",
                UserWarning,
            )

        # 检查 JWT_SECRET_KEY 长度
        if len(self.JWT_SECRET_KEY) < self.JWT_SECRET_KEY_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY 长度必须至少 {self.JWT_SECRET_KEY_MIN_LENGTH} 位！\n"
                f"当前长度: {len(self.JWT_SECRET_KEY)}"
            )

        # 检查 DATABASE_URL
        if not self.DATABASE_URL or self.DATABASE_URL == "":
            raise ValueError("DATABASE_URL 必须配置！")

        # 生产环境安全检查
        if not self.DEBUG:
            # 检查数据库密码是否包含在 URL 中（不安全）
            if "@" in self.DATABASE_URL:
                # 提取密码部分检查
                import re

                match = re.search(r"://([^:]+):([^@]+)@", self.DATABASE_URL)
                if match:
                    db_password = match.group(2)
                    if db_password in ["password", "abc123", "root", "123456"]:
                        raise ValueError("数据库密码过于简单，存在安全风险！")

            # 生产环境必须配置 PRODUCTION_ALLOWED_HOSTS
            if not self.PRODUCTION_ALLOWED_HOSTS or self.PRODUCTION_ALLOWED_HOSTS == []:
                import warnings
                warnings.warn(
                    "生产环境未配置 PRODUCTION_ALLOWED_HOSTS，CORS 可能受限！",
                    UserWarning
                )

        return self

    @property
    def cors_allowed_hosts(self) -> List[str]:
        """获取当前环境适用的 CORS 允许域名列表"""
        if not self.DEBUG and self.PRODUCTION_ALLOWED_HOSTS:
            # 生产环境使用生产环境配置
            if isinstance(self.PRODUCTION_ALLOWED_HOSTS, str):
                return [h.strip() for h in self.PRODUCTION_ALLOWED_HOSTS.split(",") if h.strip()]
            return self.PRODUCTION_ALLOWED_HOSTS
        # 开发环境使用开发环境配置
        if isinstance(self.ALLOWED_HOSTS, str):
            return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]
        return self.ALLOWED_HOSTS


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例
    使用 lru_cache 避免重复读取环境变量
    """
    return Settings()


settings = get_settings()
