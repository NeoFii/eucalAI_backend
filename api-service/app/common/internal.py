"""HMAC client (sender side) for cross-service internal HTTP calls.

Ported from admin-service `src/common/internal.py` in Plan 05-01 / Task 1b
(Pitfall 1). Public API mirrors the source verbatim:

    - get_internal_client / close_internal_clients
    - request_internal_json / get_internal_json
    - reset_internal_circuit_breakers
    - InternalServiceError + 3 subclasses
    - INTERNAL_CALLER_HEADER, INTERNAL_TIMESTAMP_HEADER, INTERNAL_SIGNATURE_HEADER

Rewrites from source:
    - `from common.observability import ...` →
      `from app.common.observability import ...`
    - Canonical signing helpers + header constants are imported from
      `app.common.http.internal_signing` so the sender does NOT
      redefine them (Pitfall 1 dedupe — single source of truth shared with
      the receiver-side `common/http/internal_auth.py`).

Plan 05-03 will consume `get_internal_json` for the inference-service log
fetch. The module is dormant until then (no live callers in Wave 1).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from fastapi import status

from app.common.http.internal_signing import (
    INTERNAL_CALLER_HEADER,
    INTERNAL_SIGNATURE_HEADER,
    INTERNAL_TIMESTAMP_HEADER,
    _build_internal_signature,
    _canonicalize_json_body,
    _canonicalize_request_target,
)
from app.common.observability import (
    REQUEST_ID_HEADER,
    TRACE_ID_HEADER,
    get_request_id,
    get_trace_id,
)

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class InternalServiceError(httpx.HTTPError):
    """Base exception for internal service transport and availability failures."""

    def __init__(
        self,
        message: str,
        *,
        target_service: str,
        path: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.target_service = target_service
        self.path = path
        self.status_code = status_code


class InternalServiceUnavailableError(InternalServiceError):
    """Raised when an internal service is unavailable after retries."""


class InternalCircuitOpenError(InternalServiceError):
    """Raised when the local circuit breaker is open for a target service."""


class InternalServiceResponseError(InternalServiceError):
    """Raised when an internal service returns a non-retriable 4xx response."""

    def __init__(
        self,
        message: str,
        *,
        target_service: str,
        path: str,
        status_code: int,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            message,
            target_service=target_service,
            path=path,
            status_code=status_code,
        )
        self.detail = detail


# ---------------------------------------------------------------------------
# Circuit breaker state
# ---------------------------------------------------------------------------


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_until: float | None = None


_CIRCUIT_BREAKERS: dict[str, _CircuitState] = {}


def reset_internal_circuit_breakers() -> None:
    """Clear in-memory circuit-breaker state, primarily for tests."""
    _CIRCUIT_BREAKERS.clear()


def _circuit_key(target_service: str, base_url: str) -> str:
    return f"{target_service}|{base_url.rstrip('/')}"


def _get_circuit_state(key: str) -> _CircuitState:
    state = _CIRCUIT_BREAKERS.get(key)
    if state is None:
        state = _CircuitState()
        _CIRCUIT_BREAKERS[key] = state
    return state


def _check_circuit_open(*, key: str, target_service: str, path: str) -> None:
    state = _get_circuit_state(key)
    opened_until = state.opened_until
    if opened_until and opened_until > time.time():
        raise InternalCircuitOpenError(
            f"{target_service} circuit is open",
            target_service=target_service,
            path=path,
        )
    if opened_until and opened_until <= time.time():
        state.opened_until = None


def _record_success(key: str) -> None:
    state = _get_circuit_state(key)
    state.consecutive_failures = 0
    state.opened_until = None


def _record_failure(
    *,
    key: str,
    threshold: int,
    cooldown_seconds: float,
) -> None:
    state = _get_circuit_state(key)
    state.consecutive_failures += 1
    if threshold > 0 and state.consecutive_failures >= threshold:
        state.opened_until = time.time() + max(cooldown_seconds, 0.0)


# ---------------------------------------------------------------------------
# Shared httpx client pool (connection reuse across requests)
# ---------------------------------------------------------------------------

_HTTP_CLIENTS: dict[str, httpx.AsyncClient] = {}


def get_internal_client(base_url: str, *, timeout: float = 10.0) -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient keyed on `base_url`.

    The client is reused across requests so connection pools survive. Closed
    via `close_internal_clients()` in the app shutdown hook.
    """
    key = base_url.rstrip("/")
    if key not in _HTTP_CLIENTS:
        _HTTP_CLIENTS[key] = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _HTTP_CLIENTS[key]


async def close_internal_clients() -> None:
    """Gracefully close all pooled HTTP clients. Call from app shutdown."""
    for client in _HTTP_CLIENTS.values():
        await client.aclose()
    _HTTP_CLIENTS.clear()


# ---------------------------------------------------------------------------
# Signed request helpers
# ---------------------------------------------------------------------------


def _build_internal_headers(
    *,
    secret: str,
    caller_service: str,
    method: str,
    path: str,
    json_body: dict | None = None,
    query_params: dict | list[tuple[str, object]] | None = None,
) -> dict[str, str]:
    """Build the canonical headers for an internal service call."""
    timestamp = str(int(time.time()))
    canonical_body = _canonicalize_json_body(json_body)
    request_target = _canonicalize_request_target(path, query_params=query_params)
    headers = {
        INTERNAL_CALLER_HEADER: caller_service,
        INTERNAL_TIMESTAMP_HEADER: timestamp,
        INTERNAL_SIGNATURE_HEADER: _build_internal_signature(
            secret=secret,
            caller_service=caller_service,
            method=method,
            request_target=request_target,
            timestamp=timestamp,
            canonical_body=canonical_body,
        ),
    }
    request_id = get_request_id()
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    trace_id = get_trace_id()
    if trace_id:
        headers[TRACE_ID_HEADER] = trace_id
    return headers


def _build_internal_url(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url.rstrip('/')}{normalized_path}"


def _extract_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if detail is not None:
            return str(detail)

    text = getattr(response, "text", "")
    if text:
        return text.strip() or None
    return None


async def request_internal_json(
    *,
    method: str,
    base_url: str,
    target_service: str,
    path: str,
    secret: str,
    caller_service: str,
    timeout: float,
    json_body: dict | None = None,
    query_params: dict | list[tuple[str, object]] | None = None,
    allow_404: bool = False,
    max_retries: int = 1,
    retry_backoff_seconds: float = 0.2,
    circuit_breaker_threshold: int = 3,
    circuit_breaker_cooldown_seconds: float = 30.0,
) -> dict | None:
    """Perform a canonical internal request and decode JSON.

    Raises `InternalServiceUnavailableError` on retriable failures,
    `InternalCircuitOpenError` if the breaker is open, and
    `InternalServiceResponseError` for non-retriable 4xx responses.
    """
    attempts = max(max_retries, 0) + 1
    url = _build_internal_url(base_url, path)
    breaker_key = _circuit_key(target_service, base_url)

    _check_circuit_open(key=breaker_key, target_service=target_service, path=path)

    for attempt in range(attempts):
        try:
            client = get_internal_client(base_url, timeout=timeout)
            response = await client.request(
                method,
                url,
                headers=_build_internal_headers(
                    secret=secret,
                    caller_service=caller_service,
                    method=method,
                    path=path,
                    json_body=json_body,
                    query_params=query_params,
                ),
                json=json_body,
                params=query_params,
            )
        except httpx.HTTPError as exc:
            if attempt == attempts - 1:
                _record_failure(
                    key=breaker_key,
                    threshold=circuit_breaker_threshold,
                    cooldown_seconds=circuit_breaker_cooldown_seconds,
                )
                raise InternalServiceUnavailableError(
                    f"{target_service} request failed",
                    target_service=target_service,
                    path=path,
                ) from exc
            await asyncio.sleep(retry_backoff_seconds * (attempt + 1))
            continue

        if allow_404 and response.status_code == status.HTTP_404_NOT_FOUND:
            _record_success(breaker_key)
            return None
        if response.status_code >= 500 and attempt < attempts - 1:
            await asyncio.sleep(retry_backoff_seconds * (attempt + 1))
            continue
        if response.status_code >= 500:
            _record_failure(
                key=breaker_key,
                threshold=circuit_breaker_threshold,
                cooldown_seconds=circuit_breaker_cooldown_seconds,
            )
            raise InternalServiceUnavailableError(
                f"{target_service} returned {response.status_code}",
                target_service=target_service,
                path=path,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            _record_success(breaker_key)
            detail = _extract_error_detail(response)
            raise InternalServiceResponseError(
                f"{target_service} returned {response.status_code}",
                target_service=target_service,
                path=path,
                status_code=response.status_code,
                detail=detail,
            )
        _record_success(breaker_key)
        try:
            return response.json()
        except ValueError as exc:
            _record_failure(
                key=breaker_key,
                threshold=circuit_breaker_threshold,
                cooldown_seconds=circuit_breaker_cooldown_seconds,
            )
            raise InternalServiceUnavailableError(
                f"{target_service} returned invalid JSON",
                target_service=target_service,
                path=path,
                status_code=response.status_code,
            ) from exc

    raise RuntimeError("Internal request retry loop exited unexpectedly")


async def get_internal_json(
    *,
    base_url: str,
    target_service: str,
    path: str,
    secret: str,
    caller_service: str,
    timeout: float,
    query_params: dict | list[tuple[str, object]] | None = None,
    allow_404: bool = False,
    max_retries: int = 1,
    retry_backoff_seconds: float = 0.2,
    circuit_breaker_threshold: int = 3,
    circuit_breaker_cooldown_seconds: float = 30.0,
) -> dict | None:
    """Perform a canonical internal GET request and decode JSON."""
    return await request_internal_json(
        method="GET",
        base_url=base_url,
        target_service=target_service,
        path=path,
        secret=secret,
        caller_service=caller_service,
        timeout=timeout,
        query_params=query_params,
        allow_404=allow_404,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        circuit_breaker_threshold=circuit_breaker_threshold,
        circuit_breaker_cooldown_seconds=circuit_breaker_cooldown_seconds,
    )


__all__ = [
    "INTERNAL_CALLER_HEADER",
    "INTERNAL_SIGNATURE_HEADER",
    "INTERNAL_TIMESTAMP_HEADER",
    "InternalCircuitOpenError",
    "InternalServiceError",
    "InternalServiceResponseError",
    "InternalServiceUnavailableError",
    "close_internal_clients",
    "get_internal_client",
    "get_internal_json",
    "request_internal_json",
    "reset_internal_circuit_breakers",
]
