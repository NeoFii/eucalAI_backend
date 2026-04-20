"""Helpers for API key policy normalization and matching."""

from __future__ import annotations

from ipaddress import ip_address, ip_network


def normalize_allowed_models(value: str | None) -> str | None:
    """Normalize comma-separated allowed model names."""
    if value is None:
        return None

    raw_items = [item.strip() for item in value.split(",")]
    if not raw_items or any(not item for item in raw_items):
        raise ValueError("allowed_models must be a comma-separated list of non-empty model names")

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return ",".join(normalized)


def normalize_allow_ips(value: str | None) -> str | None:
    """Normalize newline-separated IP/CIDR rules."""
    if value is None:
        return None

    raw_items = [item.strip() for item in value.splitlines() if item.strip()]
    if not raw_items:
        raise ValueError("allow_ips must contain at least one IP address or CIDR range")

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        try:
            network = ip_network(item, strict=False)
        except ValueError as exc:
            raise ValueError("allow_ips must contain valid IP addresses or CIDR ranges") from exc
        rendered = str(network)
        if rendered not in seen:
            normalized.append(rendered)
            seen.add(rendered)
    return "\n".join(normalized)


def is_model_allowed(allowed_models: str | None, model: str) -> bool:
    """Return True when the provided model passes the policy."""
    if not allowed_models:
        return True
    return model in allowed_models.split(",")


def is_ip_allowed(allow_ips: str | None, client_ip: str) -> bool:
    """Return True when the client IP passes the policy."""
    if not allow_ips:
        return True

    try:
        parsed_ip = ip_address(client_ip)
    except ValueError:
        return False

    for item in allow_ips.splitlines():
        if not item:
            continue
        try:
            if parsed_ip in ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False
