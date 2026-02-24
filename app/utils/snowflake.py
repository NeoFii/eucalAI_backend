"""
雪花 ID 生成器
基于 snowflake-id 库实现的分布式唯一 ID 生成器

安全性评估：
1. 唯一性保证：雪花 ID 基于时间戳 + 实例 ID + 序列号
2. 时间戳顺序：生成的 ID 大致有序，不会泄露精确的生成时间
3. 分布式支持：通过 instance ID 支持多节点部署
4. 时钟回拨处理：库内部处理时钟回拨，保证 ID 唯一性

可靠性评估：
1. 库版本：使用 snowflake-id 1.0.0+，API 稳定
2. 性能：本地生成，无需网络通信，性能极高
3. 依赖：无外部依赖，纯 Python 实现
"""

from functools import lru_cache
from typing import Optional

from snowflake import SnowflakeGenerator

from app.config import settings


def _get_instance_id() -> int:
    """
    生成 instance ID
    将 datacenter_id 和 worker_id 组合成一个 instance ID

    组合方式：datacenter_id * 32 + worker_id
    这样 datacenter_id (0-31) 和 worker_id (0-31) 可以组合成唯一的 instance_id
    """
    return settings.SNOWFLAKE_DATACENTER_ID * 32 + settings.SNOWFLAKE_WORKER_ID


@lru_cache()
def get_snowflake_generator() -> SnowflakeGenerator:
    """
    获取雪花 ID 生成器单例
    使用 lru_cache 确保全局只有一个生成器实例

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

    Example:
        >>> uid = generate_snowflake_id()
        >>> print(uid)
        1387263847263847263
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
        dc = datacenter_id if datacenter_id is not None else settings.SNOWFLAKE_DATACENTER_ID
        wk = worker_id if worker_id is not None else settings.SNOWFLAKE_WORKER_ID
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


# 全局生成器实例
generator = SnowflakeIDGenerator()
