"""RuntimeConfigStore: hot-reloadable runtime configuration."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any, Dict, List, Tuple

from core.config import (
    DEFAULT_ROUTER_ALIAS,
    FIVEWAY_DEFAULT_WEIGHTS,
    FIVEWAY_ROUTE_ORDER,
)

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_logger = logging.getLogger("router_service")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} references with environment variable values."""
    def _replace(m: re.Match) -> str:
        env_val = os.environ.get(m.group(1))
        if env_val is None:
            raise ValueError(
                f"environment variable {m.group(1)} is not set (referenced in runtime config)"
            )
        return env_val
    return _ENV_VAR_RE.sub(_replace, value)


def parse_score_bands(raw: str) -> List[Tuple[float, float, int]]:
    bands: List[Tuple[float, float, int]] = []
    for item in raw.split(","):
        left, _, right = item.partition(":")
        if not left or not right:
            continue
        tier = int(right.strip())
        if "-" in left:
            start_raw, _, end_raw = left.partition("-")
            start = float(start_raw.strip())
            end = float(end_raw.strip())
        else:
            start = end = float(left.strip())
        if start > end:
            raise ValueError("score band start must be <= end")
        bands.append((start, end, tier))
    if not bands:
        raise ValueError("score bands must not be empty")
    return bands


def build_default_runtime_config() -> Dict[str, Any]:
    return {
        "router_alias": DEFAULT_ROUTER_ALIAS,
        "user_facing_aliases": [DEFAULT_ROUTER_ALIAS],
        "route_order": list(FIVEWAY_ROUTE_ORDER),
        "weights": dict(FIVEWAY_DEFAULT_WEIGHTS),
        "score_bands": "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1",
        "tier_model_map": {
            "1": "gpt-5-4",
            "2": "minimax-m2-7",
            "3": "qwen-3-5-397b-a17b",
            "4": "qwen3-5-flash",
            "5": "GLM4.7-Flash",
        },
        "model_providers": {},
        "model_channels": {},
        "model_prices": {},
        # NULL means "fall back to RATE_LIMIT_DEFAULT_USER_RPM env on the
        # rate_limiter side". Admin-managed value comes from the
        # routing_settings row `default_user_rpm`.
        "default_user_rpm": None,
        # System-wide hard cap. NULL means "no cap" (legacy behaviour). When
        # set, router-service applies `min(user.rpm_limit, system_rpm_cap)`.
        # Admin-managed value comes from `routing_settings.system_rpm_cap`.
        "system_rpm_cap": None,
    }


def normalize_runtime_config(raw: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base = build_default_runtime_config()
    raw = raw or {}

    route_order = raw.get("route_order") or base["route_order"]
    if route_order != FIVEWAY_ROUTE_ORDER:
        raise ValueError(f"route_order must exactly match {FIVEWAY_ROUTE_ORDER}")

    # Weights
    weights_raw = raw.get("weights", base["weights"])
    if isinstance(weights_raw, list):
        if len(weights_raw) != 5:
            raise ValueError("weights list must contain exactly 5 numbers")
        weights = dict(zip(FIVEWAY_ROUTE_ORDER, [float(x) for x in weights_raw]))
    elif isinstance(weights_raw, dict):
        weights = {}
        for name in FIVEWAY_ROUTE_ORDER:
            if name not in weights_raw:
                raise ValueError(f"weights is missing route: {name}")
            weights[name] = float(weights_raw[name])
    else:
        raise ValueError("weights must be a dict or a list")
    if any(value < 0 for value in weights.values()):
        raise ValueError("weights must be non-negative")
    if sum(weights.values()) <= 0:
        raise ValueError("weights sum must be greater than 0")

    # Score bands
    score_bands_value = raw.get("score_bands", base["score_bands"])
    score_bands_raw_fallback = str(raw.get("score_bands_raw", "")).strip()
    if isinstance(score_bands_value, list):
        score_bands: List[Tuple[float, float, int]] = []
        for item in score_bands_value:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                raise ValueError("score_bands list items must be [start, end, tier]")
            score_bands.append((float(item[0]), float(item[1]), int(item[2])))
        if not score_bands:
            raise ValueError("score bands must not be empty")
        if score_bands_raw_fallback:
            score_bands_raw = score_bands_raw_fallback
        else:
            pieces = []
            for start, end, tier in score_bands:
                pieces.append(f"{start}-{end}:{tier}" if start != end else f"{start}:{tier}")
            score_bands_raw = ",".join(pieces)
    else:
        score_bands_raw = str(score_bands_value).strip()
        score_bands = parse_score_bands(score_bands_raw)

    # Tier model map
    tier_map_raw = raw.get("tier_model_map", base["tier_model_map"])
    if not isinstance(tier_map_raw, dict):
        raise ValueError("tier_model_map must be a dict")
    tier_model_map: Dict[int, str] = {}
    for key, value in tier_map_raw.items():
        tier = int(key)
        model_name = str(value).strip()
        if not model_name:
            raise ValueError("tier_model_map values must not be empty")
        tier_model_map[tier] = model_name
    if set(tier_model_map) != {1, 2, 3, 4, 5}:
        raise ValueError("tier_model_map must define tiers 1..5")

    router_alias = str(raw.get("router_alias", base["router_alias"])).strip() or DEFAULT_ROUTER_ALIAS

    # User-facing aliases — entries the API client may put in the `model` field.
    # Accept either a list (preferred, sent by admin-service) or a comma-string
    # (defensive fallback). The router_alias itself is always included so admins
    # can never accidentally lock out the auto entry.
    raw_aliases = raw.get("user_facing_aliases", [router_alias])
    if isinstance(raw_aliases, str):
        alias_list = [a.strip() for a in raw_aliases.split(",") if a.strip()]
    elif isinstance(raw_aliases, (list, tuple)):
        alias_list = [str(a).strip() for a in raw_aliases if str(a).strip()]
    else:
        alias_list = []
    if not alias_list:
        alias_list = [router_alias]
    if router_alias not in alias_list:
        alias_list.insert(0, router_alias)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    user_facing_aliases: List[str] = []
    for alias in alias_list:
        if alias not in seen:
            seen.add(alias)
            user_facing_aliases.append(alias)

    # Model providers
    providers_raw = raw.get("model_providers", base["model_providers"])
    if not isinstance(providers_raw, dict):
        raise ValueError("model_providers must be a dict")
    model_providers: Dict[str, Dict[str, str]] = {}
    for model_name, prov in providers_raw.items():
        if not isinstance(prov, dict):
            raise ValueError(f"model_providers[{model_name}] must be a dict")
        for key in ("provider_slug", "api_key", "api_base", "upstream_model"):
            if key not in prov or not str(prov[key]).strip():
                raise ValueError(f"model_providers[{model_name}] missing {key}")
        model_providers[str(model_name).strip()] = {
            "provider_slug": str(prov["provider_slug"]).strip(),
            "api_key": _resolve_env_vars(str(prov["api_key"]).strip()),
            "api_base": _resolve_env_vars(str(prov["api_base"]).strip()),
            "upstream_model": str(prov["upstream_model"]).strip(),
        }
        resolved_key = model_providers[str(model_name).strip()]["api_key"]
        if not resolved_key or "${" in resolved_key:
            raise ValueError(
                f"model_providers[{model_name}].api_key resolved to empty or unresolved value"
            )

    # Model channels (v2 format from admin-service)
    model_channels_raw = raw.get("model_channels", {})
    model_channels: Dict[str, list] = {}
    if isinstance(model_channels_raw, dict):
        for model_name, channels in model_channels_raw.items():
            if not isinstance(channels, list):
                continue
            validated = []
            for ch in channels:
                if not isinstance(ch, dict):
                    continue
                for key in ("channel_slug", "provider_slug", "api_key", "api_base", "upstream_model"):
                    if key not in ch or not str(ch[key]).strip():
                        raise ValueError(f"model_channels[{model_name}] channel missing {key}")
                validated.append({
                    "channel_slug": str(ch["channel_slug"]).strip(),
                    "provider_slug": str(ch["provider_slug"]).strip(),
                    "api_key": str(ch["api_key"]).strip(),
                    "api_base": str(ch["api_base"]).strip(),
                    "upstream_model": str(ch["upstream_model"]).strip(),
                    "priority": int(ch.get("priority", 0)),
                    "weight": int(ch.get("weight", 1)),
                    "input_price_per_million": int(ch.get("input_price_per_million", 0)),
                    "output_price_per_million": int(ch.get("output_price_per_million", 0)),
                    "cached_input_price_per_million": int(ch.get("cached_input_price_per_million", 0)),
                    "pool_account_id": ch.get("pool_account_id"),
                    "rpm_limit": ch.get("rpm_limit"),
                    "tpm_limit": ch.get("tpm_limit"),
                })
            if validated:
                model_channels[str(model_name).strip()] = validated

    # Model prices (user-facing, from supported_models)
    model_prices_raw = raw.get("model_prices", {})
    model_prices: Dict[str, Dict[str, int]] = {}
    if isinstance(model_prices_raw, dict):
        for model_name, prices in model_prices_raw.items():
            if isinstance(prices, dict):
                model_prices[str(model_name).strip()] = {
                    "input": int(prices.get("input", 0)),
                    "output": int(prices.get("output", 0)),
                    "cached_input": int(prices.get("cached_input", 0)),
                }

    return {
        "router_alias": router_alias,
        "user_facing_aliases": user_facing_aliases,
        "route_order": list(FIVEWAY_ROUTE_ORDER),
        "weights": weights,
        "score_bands_raw": score_bands_raw,
        "score_bands": score_bands,
        "tier_model_map": tier_model_map,
        "model_providers": model_providers,
        "model_channels": model_channels,
        "model_prices": model_prices,
        "default_user_rpm": _coerce_default_user_rpm(raw.get("default_user_rpm")),
        "system_rpm_cap": _coerce_default_user_rpm(raw.get("system_rpm_cap")),
    }


def _coerce_default_user_rpm(value: Any) -> int | None:
    """Coerce admin-supplied RPM ints (default_user_rpm, system_rpm_cap) to a
    positive int, else None.

    Shared coercer for both fields since they have identical semantics:
    None means "no override / fall back to env or no cap". Bad values silently
    degrade to None rather than crashing config refresh.
    """
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


class RuntimeConfigStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._cached: Dict[str, Any] | None = None

    def ensure_exists(self) -> None:
        if os.path.exists(self.path):
            return
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(build_default_runtime_config(), f, ensure_ascii=False, indent=2)

    def load(self) -> Dict[str, Any]:
        self.ensure_exists()
        mtime = os.path.getmtime(self.path)
        with self._lock:
            if self._cached is not None and self._mtime == mtime:
                return self._cached
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                config = normalize_runtime_config(raw)
            except Exception:
                if self._cached is not None:
                    _logger.warning(
                        "failed to reload %s, using last valid config", self.path,
                        exc_info=True,
                    )
                    return self._cached
                raise
            self._cached = config
            self._mtime = mtime
            return config

    async def aload(self) -> Dict[str, Any]:
        """Async wrapper that offloads file I/O to a thread."""
        import asyncio
        return await asyncio.to_thread(self.load)
