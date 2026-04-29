"""Redis-backed token blacklist for JWT revocation."""

from __future__ import annotations

import logging

from common.redis import get_redis

logger = logging.getLogger(__name__)

_PREFIX = "token:bl:"


async def blacklist_token(token_hash: str, ttl_seconds: int) -> bool:
    """Add a token hash to the blacklist. Returns True on success, False on Redis failure."""
    if ttl_seconds <= 0:
        return False
    try:
        await get_redis().set(f"{_PREFIX}{token_hash}", "1", ex=ttl_seconds)
    except Exception:
        logger.critical("Failed to blacklist token %s — Redis unavailable", token_hash, exc_info=True)
        return False
    return True


async def is_token_blacklisted(token_hash: str) -> bool:
    """Check whether a token hash has been revoked. Fail-open on Redis errors."""
    try:
        return bool(await get_redis().exists(f"{_PREFIX}{token_hash}"))
    except Exception:
        logger.warning("Redis unavailable for blacklist check — failing open", exc_info=True)
        return False
