"""
雪花 ID 生成器
基于 snowflake-id 库实现的分布式唯一 ID 生成器
"""

from functools import lru_cache
from typing import Optional

from snowflake import SnowflakeGenerator

# 全局配置（由各服务初始化时设置）
_snowflake_config = {
    "worker_id": 1,
    "datacenter_id": 1,
}


def configure_snowflake(worker_id: int = 1, datacenter_id: int = 1) -> None:
    """
    配置雪花 ID 生成器

    Args:
        worker_id: 工作节点 ID（0-31）
        datacenter_id: 数据中心 ID（0-31）
    """
    _snowflake_config["worker_id"] = worker_id
    _snowflake_config["datacenter_id"] = datacenter_id
    # 清除缓存，使新的配置生效
    get_snowflake_generator.cache_clear()


def _get_instance_id() -> int:
    """
    生成 instance ID
    将 datacenter_id 和 worker_id 组合成一个 instance ID
    """
    return _snowflake_config["datacenter_id"] * 32 + _snowflake_config["worker_id"]


@lru_cache()
def get_snowflake_generator() -> SnowflakeGenerator:
    """
    获取雪花 ID 生成器单例

    Returns:
        SnowflakeGenerator: 雪花 ID 生成器
    """
    instance_id = _get_instance_id()
    return SnowflakeGenerator(instance=instance_id)


def generate_snowflake_id() -> int:
    """
    生成雪花 ID

    Returns:
        int: 64 位唯一 ID
    """
    generator = get_snowflake_generator()
    return next(generator)


class SnowflakeIDGenerator:
    """
    雪花 ID 生成器类
    提供面向对象的接口
    """

    def __init__(
        self,
        datacenter_id: Optional[int] = None,
        worker_id: Optional[int] = None,
    ):
        """
        初始化雪花 ID 生成器

        Args:
            datacenter_id: 数据中心 ID（0-31），默认从配置读取
            worker_id: 工作节点 ID（0-31），默认从配置读取
        """
        dc = datacenter_id if datacenter_id is not None else _snowflake_config["datacenter_id"]
        wk = worker_id if worker_id is not None else _snowflake_config["worker_id"]
        instance_id = dc * 32 + wk
        self._generator = SnowflakeGenerator(instance=instance_id)

    def generate(self) -> int:
        """生成雪花 ID"""
        return next(self._generator)

    def generate_batch(self, count: int) -> list:
        """
        批量生成雪花 ID

        Args:
            count: 生成数量

        Returns:
            list: 雪花 ID 列表
        """
        return [next(self._generator) for _ in range(count)]
