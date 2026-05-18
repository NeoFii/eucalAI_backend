"""Email normalization helpers for api-service."""

from __future__ import annotations


def normalize_email(email: str) -> str:
    """Normalize user-facing email input for consistent storage and lookup."""
    return email.strip().lower()
