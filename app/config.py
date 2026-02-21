"""
应用配置管理
使用 Pydantic Settings 管理环境变量
"""

from functools import lru_cache
from typing import List

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
    DEBUG: bool = True

    # CORS 配置 - 前后端分离，允许前端域名访问
    ALLOWED_HOSTS: List[str] = [
        "http://localhost:5173",   # Vite 开发服务器
        "http://localhost:3000",   # 其他前端开发端口
        "http://127.0.0.1:5173",
    ]

    # 时区设置
    TIMEZONE: str = "Asia/Shanghai"

    # 联系表单配置
    CONTACT_EMAIL_TO: str = "contact@eucal.ai"  # 接收联系表单的目标邮箱
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例
    使用 lru_cache 避免重复读取环境变量
    """
    return Settings()


settings = get_settings()
