"""Internal service authentication — signature verification (receiver side).

Only contains the verification/dependency logic for protecting internal endpoints.
Calling-side logic (httpx pool, circuit breaker, request helpers) is NOT included here;
it will be handled by InferenceClient in Phase 6.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Header, HTTPException, Request, status

INTERNAL_CALLER_HEADER = "X-Internal-Service"
INTERNAL_TIMESTAMP_HEADER = "X-Internal-Timestamp"
INTERNAL_SIGNATURE_HEADER = "X-Internal-Signature"
INVALID_INTERNAL_SECRET_DETAIL = "Invalid internal secret"
INVALID_INTERNAL_CALLER_DETAIL = "Invalid internal caller"


def _canonicalize_request_body(body: bytes) -> str:
    if not body:
        return ""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="ignore")
    if parsed is None:
        return ""
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonicalize_query_pairs(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    normalized = sorted((str(key), str(value)) for key, value in pairs)
    return urlencode(normalized, doseq=True)


def _canonicalize_request_query(raw_query: str) -> str:
    if not raw_query:
        return ""
    return _canonicalize_query_pairs(parse_qsl(raw_query, keep_blank_values=True))


def _canonicalize_request_target(path: str, *, raw_query: str = "") -> str:
    split = urlsplit(path)
    normalized_path = split.path or path or "/"
    query = _canonicalize_request_query(raw_query or split.query)
    if query:
        return f"{normalized_path}?{query}"
    return normalized_path


def _build_internal_signature(
    *,
    secret: str,
    caller_service: str,
    method: str,
    request_target: str,
    timestamp: str,
    canonical_body: str,
) -> str:
    body_digest = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
    payload = f"{caller_service}|{method.upper()}|{request_target}|{timestamp}|{body_digest}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


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
