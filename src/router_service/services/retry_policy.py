"""Retry and auto-disable decision logic for upstream channel errors."""

from __future__ import annotations

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503})

NEVER_RETRY_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404})

AUTO_DISABLE_STATUS_CODES: frozenset[int] = frozenset({401, 403})

AUTO_DISABLE_KEYWORDS: tuple[str, ...] = (
    "credit balance too low",
    "quota exceeded",
    "insufficient_quota",
    "insufficient quota",
    "account deactivated",
    "account disabled",
    "permission denied",
    "security token included in the request is invalid",
)


def extract_status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    return None


def should_retry(exc: Exception, status_code: int | None = None) -> bool:
    if status_code is None:
        status_code = extract_status_code(exc)
    if status_code is None:
        return True
    if status_code in NEVER_RETRY_STATUS_CODES:
        return False
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    if 500 <= status_code < 600:
        return True
    return False


def should_auto_disable(exc: Exception, status_code: int | None = None) -> bool:
    if status_code is None:
        status_code = extract_status_code(exc)
    if status_code is not None and status_code in AUTO_DISABLE_STATUS_CODES:
        return True
    msg = str(exc).lower()
    return any(kw in msg for kw in AUTO_DISABLE_KEYWORDS)
