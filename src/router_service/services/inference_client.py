"""HTTP client for inference-service /internal/v1/classify."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException

logger = logging.getLogger("router_service")


class InferenceClient:
    """Async HTTP client that calls inference-service for routing decisions."""

    def __init__(self, base_url: str, secret: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

    async def classify(
        self,
        messages: List[Dict[str, Any]],
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if self._secret:
            headers["X-Inference-Secret"] = self._secret

        payload: Dict[str, Any] = {"messages": messages}
        if request_id:
            payload["request_id"] = request_id

        try:
            resp = await self._client.post(
                "/internal/v1/classify",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "inference-service returned %s: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            raise HTTPException(
                status_code=503, detail="inference service unavailable"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.error("inference-service unreachable: %s", exc)
            raise HTTPException(
                status_code=503, detail="inference service unavailable"
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()
