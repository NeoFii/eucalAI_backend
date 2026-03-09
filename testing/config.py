# -*- coding: utf-8 -*-
"""
Testing 服务配置
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Testing 服务配置"""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库 - 优先使用 DATABASE_URL（兼容现有配置）
    database_url: str = ""

    # 服务
    host: str = "0.0.0.0"
    port: int = 8002

    # 基准测试默认配置
    benchmark_default_timeout: int = 60
    benchmark_default_concurrency: int = 10
    benchmark_default_rate_limit: int = 60

    # 缓存配置
    cache_ttl_short: int = 300  # 5分钟
    cache_ttl_long: int = 86400  # 24小时

    def get_database_url(self) -> str:
        """获取数据库 URL，优先使用 DATABASE_URL"""
        if self.database_url:
            return self.database_url
        return os.environ.get("DATABASE_URL", "") or os.environ.get("TESTING_DATABASE_URL", "")


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
