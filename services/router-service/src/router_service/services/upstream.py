"""Upstream model invocation: resolve provider target + litellm call helpers."""

from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import urlparse

_BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "metadata.google.internal", "169.254.169.254",
})


def _validate_upstream_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"upstream URL must use http/https, got: {parsed.scheme}")
    hostname = (parsed.hostname or "").lower()
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"upstream URL targets blocked host: {hostname}")
    if hostname.startswith("10.") or hostname.startswith("192.168."):
        raise ValueError(f"upstream URL targets private network: {hostname}")
    if hostname.startswith("172."):
        parts = hostname.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    raise ValueError(f"upstream URL targets private network: {hostname}")
            except ValueError:
                pass


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
    _validate_upstream_url(api_base)

    return {
        "logical_model": logical_model,
        "provider_slug": config["provider_slug"],
        "api_key": api_key,
        "api_base": api_base,
        "upstream_model": upstream_model,
    }


def resolve_model_channel_target(
    logical_model: str,
    model_channels: Dict[str, list],
    channel_selector: Any,
    *,
    excluded_slugs: frozenset[str] | None = None,
    retry_tier: int = 0,
    rate_limited_accounts: frozenset[int] | None = None,
) -> Dict[str, str]:
    """Resolve a model to a specific channel from the pool."""
    channels = model_channels.get(logical_model)
    if not channels:
        raise KeyError(f"no channels available for model: {logical_model}")

    selected = channel_selector.select(
        logical_model, channels,
        excluded_slugs=excluded_slugs, retry_tier=retry_tier,
        rate_limited_accounts=rate_limited_accounts,
    )
    api_base = normalize_api_base(str(selected["api_base"]))
    api_key = str(selected["api_key"]).strip()
    upstream_model = str(selected["upstream_model"]).strip()

    if not api_key:
        raise ValueError(f"missing api_key for channel {selected.get('channel_slug')}")
    if not api_base:
        raise ValueError(f"missing api_base for channel {selected.get('channel_slug')}")
    _validate_upstream_url(api_base)

    return {
        "logical_model": logical_model,
        "channel_slug": selected["channel_slug"],
        "provider_slug": selected["provider_slug"],
        "api_key": api_key,
        "api_base": api_base,
        "upstream_model": upstream_model,
        "input_price_per_million": selected.get("input_price_per_million", 0),
        "output_price_per_million": selected.get("output_price_per_million", 0),
        "cached_input_price_per_million": selected.get("cached_input_price_per_million", 0),
        "pool_account_id": selected.get("pool_account_id"),
        "rpm_limit": selected.get("rpm_limit"),
    }


_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags and their content."""
    return _THINK_TAG_RE.sub("", text).strip()
