"""API Key authentication for relay hot path — three-tier: TTLCache -> Redis -> DB.

Eliminates all HTTP calls to user-service for API Key validation (RELAY-05).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

import cachetools
from fastapi import Header, HTTPException, Request

from app.common.infra.cache import get_cache_redis
from app.core.config import settings
from app.core.db import get_db_context

logger = logging.getLogger(__name__)

# ── In-process TTL cache (Tier 1) ────────────────────────────────────────────
_api_key_cache: cachetools.TTLCache[str, "ValidatedApiKey"] = cachetools.TTLCache(
    maxsize=settings.RELAY_TOKEN_CACHE_MAXSIZE,
    ttl=settings.RELAY_TOKEN_CACHE_TTL,
)


@dataclass(slots=True)
class ValidatedApiKey:
    """Minimal API-key principal for relay auth."""

    id: int
    user_id: int
    key_hash: str
    status: int
    user_rpm_limit: int | None = None
    balance: int = 0


def invalidate_api_key_cache(key_hash: str) -> None:
    """Remove a key from the in-process cache (D-07 active invalidation)."""
    _api_key_cache.pop(key_hash, None)


def _build_principal(api_key) -> ValidatedApiKey:
    """Build ValidatedApiKey from ORM UserApiKey instance."""
    return ValidatedApiKey(
        id=api_key.id,
        user_id=api_key.user_id,
        key_hash=api_key.key_hash,
        status=api_key.status,
        user_rpm_limit=getattr(api_key, "user_rpm_limit", None),
    )


def _principal_to_json(principal: ValidatedApiKey) -> str:
    """Serialize principal to JSON for Redis storage."""
    return json.dumps(
        {
            "id": principal.id,
            "user_id": principal.user_id,
            "key_hash": principal.key_hash,
            "status": principal.status,
            "user_rpm_limit": principal.user_rpm_limit,
        },
        ensure_ascii=False,
    )


def _principal_from_json(data: str) -> ValidatedApiKey:
    """Deserialize principal from Redis JSON."""
    d = json.loads(data)
    return ValidatedApiKey(
        id=d["id"],
        user_id=d["user_id"],
        key_hash=d["key_hash"],
        status=d["status"],
        user_rpm_limit=d.get("user_rpm_limit"),
    )


async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> ValidatedApiKey:
    """FastAPI dependency: validate API key via TTLCache -> Redis -> DB.

    Raises HTTPException 401 for missing/invalid key, 403 for disabled.
    """
    bearer = (authorization or "").strip()
    raw_key: str | None = None
    if bearer.lower().startswith("bearer ") and bearer[7:].strip():
        raw_key = bearer[7:].strip()
    elif x_api_key and str(x_api_key).strip():
        raw_key = str(x_api_key).strip()
    if not raw_key:
        raise HTTPException(status_code=401, detail="missing api key")

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # ── Tier 1: in-process TTLCache ──────────────────────────────────────
    cached = _api_key_cache.get(key_hash)
    if cached is not None:
        return cached

    # ── Tier 2: Redis (shared across requests in same worker) ────────────
    try:
        cache_redis = get_cache_redis()
        redis_val = await cache_redis.get(f"token:{key_hash}")
        if redis_val is not None:
            principal = _principal_from_json(redis_val)
            _api_key_cache[key_hash] = principal
            return principal
    except Exception:
        logger.debug("Redis unavailable for token lookup, falling back to DB")

    # ── Tier 3: DB (authoritative source) ────────────────────────────────
    from app.common.core.exceptions import (
        ApiKeyDisabledException,
        ApiKeyNotFoundException,
        UserDisabledException,
    )
    from app.service.api_key_service import ApiKeyService

    try:
        async with get_db_context() as db:
            api_key = await ApiKeyService.validate_by_hash(db, key_hash)
    except ApiKeyNotFoundException:
        raise HTTPException(status_code=401, detail="invalid api key")
    except (ApiKeyDisabledException, UserDisabledException) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    principal = _build_principal(api_key)

    # Write-back to Redis (best-effort)
    try:
        cache_redis = get_cache_redis()
        await cache_redis.set(
            f"token:{key_hash}",
            _principal_to_json(principal),
            ex=settings.RELAY_TOKEN_CACHE_TTL,
        )
    except Exception:
        logger.debug("Redis write-back failed for token:%s", key_hash[:8])

    _api_key_cache[key_hash] = principal
    return principal


__all__ = ["ValidatedApiKey", "invalidate_api_key_cache", "require_api_key"]
