"""HTTP client for inference-service /internal/v1/classify."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import httpx

from common.observability import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger("router_service")


@dataclass
class ClassifyResult:
    success: bool
    data: Dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None

class InferenceClient:
    """Async HTTP client that calls inference-service for routing decisions.

    Includes simple retry (5xx/connection errors only) and circuit breaker.
    """

    def __init__(
        self,
        base_url: str,
        secret: str,
        timeout: float = 10.0,
        max_retries: int = 1,
        retry_backoff: float = 0.2,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._cb_threshold = circuit_breaker_threshold
        self._cb_cooldown = circuit_breaker_cooldown
        self._cb_failures = 0
        self._cb_open_until: float = 0.0
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

    def _check_circuit_breaker(self) -> ClassifyResult | None:
        if self._cb_failures >= self._cb_threshold:
            if time.monotonic() < self._cb_open_until:
                return ClassifyResult(
                    success=False,
                    error_code="circuit_open",
                    error_message="inference service circuit breaker open",
                )
            self._cb_failures = 0
        return None

    def _record_success(self) -> None:
        self._cb_failures = 0

    def _record_failure(self) -> None:
        self._cb_failures += 1
        if self._cb_failures >= self._cb_threshold:
            self._cb_open_until = time.monotonic() + self._cb_cooldown
            logger.warning(
                "inference-service circuit breaker opened after %d failures, cooldown %.1fs",
                self._cb_failures, self._cb_cooldown,
            )

    async def classify(
        self,
        messages: List[Dict[str, Any]],
        request_id: str | None = None,
    ) -> ClassifyResult:
        cb_result = self._check_circuit_breaker()
        if cb_result is not None:
            return cb_result

        headers: Dict[str, str] = {}
        if self._secret:
            headers["X-Inference-Secret"] = self._secret
        rid = get_request_id()
        if rid:
            headers[REQUEST_ID_HEADER] = rid

        payload: Dict[str, Any] = {"messages": messages}
        if request_id:
            payload["request_id"] = request_id

        last_exc: Exception | None = None
        attempts = 1 + self._max_retries

        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    "/internal/v1/classify",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code < 400:
                    self._record_success()
                    return ClassifyResult(success=True, data=resp.json(), http_status=resp.status_code)

                parsed_error = self._parse_error_response(resp)
                if resp.status_code < 500:
                    self._record_success()
                    return ClassifyResult(
                        success=False,
                        error_code=parsed_error[0],
                        error_message=parsed_error[1],
                        http_status=resp.status_code,
                    )

                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                logger.warning(
                    "inference-service returned %s (attempt %d/%d)",
                    resp.status_code, attempt + 1, attempts,
                )
                if attempt == attempts - 1:
                    self._record_failure()
                    return ClassifyResult(
                        success=False,
                        error_code=parsed_error[0],
                        error_message=parsed_error[1],
                        http_status=resp.status_code,
                    )
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "inference-service returned %s (attempt %d/%d)",
                    exc.response.status_code, attempt + 1, attempts,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    "inference-service unreachable: %s (attempt %d/%d)",
                    exc, attempt + 1, attempts,
                )

            if attempt < attempts - 1:
                await asyncio.sleep(self._retry_backoff)

        self._record_failure()
        logger.error("inference-service failed after %d attempts: %s", attempts, last_exc)
        return ClassifyResult(
            success=False,
            error_code="unavailable",
            error_message="inference service unavailable",
        )

    @staticmethod
    def _parse_error_response(resp: httpx.Response) -> tuple[str, str]:
        try:
            body = resp.json()
            if isinstance(body, dict) and "error_code" in body:
                return body["error_code"], body.get("message", "")
        except (ValueError, KeyError):
            pass
        return "unavailable", resp.text[:200] if resp.text else "unknown error"

    async def close(self) -> None:
        await self._client.aclose()
