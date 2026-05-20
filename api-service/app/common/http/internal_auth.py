"""Internal service authentication — signature verification (receiver side).

Only contains the verification/dependency logic for protecting internal endpoints.
Calling-side logic (httpx pool, circuit breaker, request helpers) is in
`app/common/internal.py` (HMAC sender). Both sides share the canonical
HMAC primitives from `app/common/http/internal_signing.py`.

Plan 05-01 / Task 1b (Pitfall 1 dedupe): the four canonicalisation helpers and
`_build_internal_signature` previously inlined here are now imported from
`internal_signing.py` so there is exactly one source of truth.
"""

from __future__ import annotations

import hmac
import time

from fastapi import Header, HTTPException, Request, status

from app.common.http.internal_signing import (
    INTERNAL_CALLER_HEADER,
    INTERNAL_SIGNATURE_HEADER,
    INTERNAL_TIMESTAMP_HEADER,
    _build_internal_signature,
    _canonicalize_request_body,
    _canonicalize_request_target,
)

INVALID_INTERNAL_SECRET_DETAIL = "Invalid internal secret"
INVALID_INTERNAL_CALLER_DETAIL = "Invalid internal caller"


def verify_internal_signature(
    *,
    secret: str,
    caller_service: str,
    method: str,
    path: str,
    raw_query: str,
    timestamp: str,
    signature: str,
    body: bytes,
    request_ttl_seconds: int = 30,
) -> bool:
    """Verify an HMAC signature from an internal service call.

    Returns True if the signature is valid and within the TTL window.
    """
    try:
        timestamp_value = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(int(time.time()) - timestamp_value) > request_ttl_seconds:
        return False

    canonical_body = _canonicalize_request_body(body)
    request_target = _canonicalize_request_target(path, raw_query=raw_query)
    expected_signature = _build_internal_signature(
        secret=secret,
        caller_service=caller_service,
        method=method,
        request_target=request_target,
        timestamp=timestamp,
        canonical_body=canonical_body,
    )
    return hmac.compare_digest(expected_signature, signature)


def build_internal_auth_dependency(
    expected_secret: str,
    *,
    request_ttl_seconds: int = 30,
    allowed_callers: set[str] | None = None,
):
    """Create a FastAPI dependency that validates signed internal service calls."""

    async def verify_internal_secret(
        request: Request,
        x_internal_service: str | None = Header(None, alias=INTERNAL_CALLER_HEADER),
        x_internal_timestamp: str | None = Header(None, alias=INTERNAL_TIMESTAMP_HEADER),
        x_internal_signature: str | None = Header(None, alias=INTERNAL_SIGNATURE_HEADER),
    ) -> None:
        if x_internal_service and x_internal_timestamp and x_internal_signature:
            try:
                timestamp_value = int(x_internal_timestamp)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=INVALID_INTERNAL_SECRET_DETAIL,
                ) from exc
            if abs(int(time.time()) - timestamp_value) > request_ttl_seconds:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=INVALID_INTERNAL_SECRET_DETAIL,
                )
            canonical_body = _canonicalize_request_body(await request.body())
            request_target = _canonicalize_request_target(
                request.url.path,
                raw_query=request.url.query,
            )
            expected_signature = _build_internal_signature(
                secret=expected_secret,
                caller_service=x_internal_service,
                method=request.method,
                request_target=request_target,
                timestamp=x_internal_timestamp,
                canonical_body=canonical_body,
            )
            if not hmac.compare_digest(expected_signature, x_internal_signature):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=INVALID_INTERNAL_SECRET_DETAIL,
                )
            if allowed_callers and x_internal_service not in allowed_callers:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=INVALID_INTERNAL_CALLER_DETAIL,
                )
            request.state.internal_caller = x_internal_service
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=INVALID_INTERNAL_SECRET_DETAIL,
        )

    return verify_internal_secret
