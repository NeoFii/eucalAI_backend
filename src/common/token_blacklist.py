"""Redis-backed token blacklist for JWT revocation."""

from __future__ import annotations

from common.redis import get_redis

_PREFIX = "token:bl:"


async def blacklist_token(token_hash: str, ttl_seconds: int) -> None:
    """Add a token hash to the blacklist with a TTL matching the token's remaining lifetime."""
    if ttl_seconds <= 0:
        return
    await get_redis().set(f"{_PREFIX}{token_hash}", "1", ex=ttl_seconds)


async def is_token_blacklisted(token_hash: str) -> bool:
    """Check whether a token hash has been revoked."""
    return bool(await get_redis().exists(f"{_PREFIX}{token_hash}"))
