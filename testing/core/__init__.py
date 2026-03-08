# -*- coding: utf-8 -*-
"""Testing 服务核心模块"""

from testing.core.cache import (
    get_or_set,
    invalidate,
    invalidate_prefix,
    long_cache,
    short_cache,
)

__all__ = [
    "get_or_set",
    "invalidate",
    "invalidate_prefix",
    "long_cache",
    "short_cache",
]
