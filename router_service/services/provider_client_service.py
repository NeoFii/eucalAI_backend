"""Provider client wrappers."""

from __future__ import annotations

from typing import Any

import litellm

from common.utils.openai_compat import normalize_openai_compatible_base_url


class RouterUpstreamError(RuntimeError):
    """Raised when upstream routing fails."""


class ProviderClientService:
    """Perform upstream chat completion calls."""

    @staticmethod
    async def chat_completion(
        *,
        model: str,
        messages: list[dict[str, Any]],
        api_key: str,
        api_base: str,
        stream: bool,
        extra_payload: dict[str, Any],
        timeout: int,
    ) -> Any:
        payload: dict[str, Any] = dict(extra_payload)
        normalized_api_base = normalize_openai_compatible_base_url(api_base)
        payload["model"] = model
        payload["messages"] = messages
        payload["api_key"] = api_key
        payload["api_base"] = normalized_api_base
        payload["base_url"] = normalized_api_base
        payload["custom_llm_provider"] = "openai"
        payload["stream"] = stream
        payload.setdefault("timeout", timeout)
        try:
            return await litellm.acompletion(**payload)
        except Exception as exc:
            raise RouterUpstreamError(str(exc)) from exc

    @staticmethod
    def normalize_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        return payload.model_dump(exclude_none=True)
