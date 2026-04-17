"""Upstream model invocation: resolve provider target + litellm call helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def normalize_api_base(value: str) -> str:
    base = (value or "").strip().rstrip("/")
    if not base:
        return base
    if base.endswith("/chat/completions"):
        return base[: -len("/chat/completions")]
    if base.endswith("/models"):
        return base[: -len("/models")]
    return base


def resolve_model_provider_target(
    logical_model: str,
    model_providers: Dict[str, Any],
) -> Dict[str, str]:
    config = model_providers.get(logical_model)
    if not config:
        raise KeyError(f"missing provider config for logical model: {logical_model}")

    api_key = str(config["api_key"]).strip()
    api_base = normalize_api_base(str(config["api_base"]))
    upstream_model = str(config["upstream_model"]).strip()
    if not api_key:
        raise ValueError(f"missing api_key for logical model {logical_model}")
    if not api_base:
        raise ValueError(f"missing api base for logical model {logical_model}")
    if not upstream_model:
        raise ValueError(f"missing upstream model for logical model {logical_model}")

    return {
        "logical_model": logical_model,
        "provider_slug": config["provider_slug"],
        "api_key": api_key,
        "api_base": api_base,
        "upstream_model": upstream_model,
    }


_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags and their content."""
    return _THINK_TAG_RE.sub("", text).strip()
