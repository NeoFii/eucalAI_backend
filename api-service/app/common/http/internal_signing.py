"""Shared HMAC signature primitives for internal service-to-service calls.

This module is the single source of the four canonicalisation + signature
helpers (`_canonicalize_request_body`, `_canonicalize_request_query`,
`_canonicalize_request_target`, `_build_internal_signature`). Both the
receiver-side dependency (`app/common/http/internal_auth.py`) and the
sender-side HMAC client (`app/common/internal.py`) import from here
— extracted out of `internal_auth.py` and the ported admin-service
`common/internal.py` in Plan 05-01 / Task 1b to eliminate the previous
duplicate function bodies (Pitfall 1 — signing-primitives dedupe).

Public API:
    - `INTERNAL_CALLER_HEADER`, `INTERNAL_TIMESTAMP_HEADER`,
      `INTERNAL_SIGNATURE_HEADER` — canonical HTTP header names.
    - `_canonicalize_json_body`, `_canonicalize_request_body`,
      `_canonicalize_query_pairs`, `_canonicalize_request_query`,
      `_canonicalize_query_params`, `_canonicalize_request_target`,
      `_build_internal_signature` — helpers used by both sender and receiver.

All function names are prefixed with `_` because the public consumer-facing
APIs are the higher-level helpers exposed by `internal_auth.py` (receiver)
and `internal.py` (sender). The underscore-prefixed names are kept stable
because the sender/receiver imports lock the symbol set.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl, urlencode, urlsplit

INTERNAL_CALLER_HEADER = "X-Internal-Service"
INTERNAL_TIMESTAMP_HEADER = "X-Internal-Timestamp"
INTERNAL_SIGNATURE_HEADER = "X-Internal-Signature"


def _canonicalize_json_body(json_body: dict | list | None) -> str:
    if json_body is None:
        return ""
    return json.dumps(json_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonicalize_request_body(body: bytes) -> str:
    if not body:
        return ""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="ignore")
    if parsed is None:
        return ""
    return _canonicalize_json_body(parsed)


def _canonicalize_query_pairs(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    normalized = sorted((str(key), str(value)) for key, value in pairs)
    return urlencode(normalized, doseq=True)


def _canonicalize_request_query(raw_query: str) -> str:
    if not raw_query:
        return ""
    return _canonicalize_query_pairs(parse_qsl(raw_query, keep_blank_values=True))


def _canonicalize_query_params(
    query_params: dict | list[tuple[str, object]] | None,
) -> str:
    if not query_params:
        return ""

    pairs: list[tuple[str, str]] = []
    items = query_params.items() if isinstance(query_params, dict) else query_params
    for key, value in items:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for entry in value:
                if entry is None:
                    continue
                pairs.append((str(key), str(entry)))
            continue
        pairs.append((str(key), str(value)))
    return _canonicalize_query_pairs(pairs)


def _canonicalize_request_target(
    path: str,
    *,
    raw_query: str = "",
    query_params: dict | list[tuple[str, object]] | None = None,
) -> str:
    split = urlsplit(path)
    normalized_path = split.path or path or "/"
    query = _canonicalize_request_query(raw_query or split.query)
    if query_params:
        query = _canonicalize_query_params(query_params)
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


__all__ = [
    "INTERNAL_CALLER_HEADER",
    "INTERNAL_SIGNATURE_HEADER",
    "INTERNAL_TIMESTAMP_HEADER",
    "_build_internal_signature",
    "_canonicalize_json_body",
    "_canonicalize_query_pairs",
    "_canonicalize_query_params",
    "_canonicalize_request_body",
    "_canonicalize_request_query",
    "_canonicalize_request_target",
]
