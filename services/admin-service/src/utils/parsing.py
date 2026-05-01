"""Shared parsing helpers for admin-service endpoints."""

from __future__ import annotations


def parse_comma_separated(value: str | None) -> list[str]:
    """Split a comma-separated query string into a trimmed, non-empty list."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]
