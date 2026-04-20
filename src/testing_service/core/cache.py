# -*- coding: utf-8 -*-
"""
进程内存缓存模块
使用 cachetools TTLCache 实现，无需 Redis 等外部依赖
"""

from cachetools import TTLCache
from typing import Any, Callable
import asyncio

# 静态数据缓存：24 小时，最多 100 条
_long_cache = TTLCache(maxsize=100, ttl=86400)
# 动态数据缓存：5 分钟，最多 500 条
_short_cache = TTLCache(maxsize=500, ttl=300)

_lock = asyncio.Lock()


async def get_or_set(
    cache: TTLCache,
    key: str,
    fn: Callable[[], Any]
) -> Any:
    """
    缓存不存在时调用 fn() 查询数据库并写入缓存

    Args:
        cache: TTLCache 实例
        key: 缓存键
        fn: 当缓存不存在时调用的函数（应为 async 函数）

    Returns:
        缓存值或 fn() 的返回值
    """
    if key in cache:
        return cache[key]

    async with _lock:
        # 双重检查，防止并发时重复查询数据库
        if key in cache:
            return cache[key]

        value = await fn()
        cache[key] = value
        return value


def invalidate(cache: TTLCache, key: str) -> None:
    """
    主动失效指定缓存键（数据更新时调用）

    Args:
        cache: TTLCache 实例
        key: 要失效的缓存键
    """
    cache.pop(key, None)


def invalidate_prefix(cache: TTLCache, prefix: str) -> None:
    """
    失效所有以指定前缀开头的缓存键

    Args:
        cache: TTLCache 实例
        prefix: 缓存键前缀
    """
    keys_to_delete = [k for k in cache.keys() if k.startswith(prefix)]
    for key in keys_to_delete:
        cache.pop(key, None)


# 对外暴露的两个缓存实例
long_cache = _long_cache
short_cache = _short_cache
